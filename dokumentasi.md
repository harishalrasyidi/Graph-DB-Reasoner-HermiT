# Dokumentasi Demo: OWL Ontology → HermiT Reasoner → Neo4j

**Studi Kasus:** Pets Ontology  
**Konteks:** Demo untuk mahasiswa D4 — memperlihatkan peran reasoner sebagai validator sebelum data masuk ke Neo4j  

---

## Daftar Isi

1. [Gambaran Besar](#1-gambaran-besar)
2. [Struktur File](#2-struktur-file)
3. [Konsep: TBox vs ABox](#3-konsep-tbox-vs-abox)
4. [Isi Ontologi (dari file .owl)](#4-isi-ontologi-dari-file-owl)
5. [Alur Program Langkah per Langkah](#5-alur-program-langkah-per-langkah)
6. [Istilah Teknis](#6-istilah-teknis)
7. [Case 1 — Ontologi Valid (pets_individuals_01.owl)](#7-case-1--ontologi-valid-pets_individuals_01owl)
8. [Case 2 — Ontologi Inkonsisten (pets_individuals_02.owl)](#8-case-2--ontologi-inkonsisten-pets_individuals_02owl)
9. [Apa yang Tersimpan di Neo4j](#9-apa-yang-tersimpan-di-neo4j)
10. [Query Eksplorasi di Neo4j Browser](#10-query-eksplorasi-di-neo4j-browser)
11. [Desain Keputusan: Kenapa Axiom Tidak Disimpan ke Neo4j](#11-desain-keputusan-kenapa-axiom-tidak-disimpan-ke-neo4j)

---

## 1. Gambaran Besar

Program ini mendemonstrasikan bagaimana **ontologi OWL berperan sebagai DDL dan validator** sebelum data individu (instances) disimpan ke Neo4j.

```
File .owl
    │
    ▼
owlready2 (load ke memori)
    │
    ▼
HermiT Reasoner
    │
    ├── KONSISTEN ──► Inferensi tipe baru ──► Simpan ke Neo4j
    │
    └── INKONSISTEN ─► Blokir ─► Neo4j tidak disentuh
```

Ada dua file demo:

| File | Isi tambahan | Hasil |
|---|---|---|
| `pets_individuals_01.owl` | Budi, Tweety, Tom, Dani | ✅ Lolos reasoner, masuk Neo4j |
| `pets_individuals_02.owl` | + Endang dan Simba | ❌ Diblokir reasoner, tidak masuk Neo4j |

---

## 2. Struktur File

```
project/
├── demo_owl_neo4j.py            ← script utama
├── pets_individuals_01.owl      ← ontologi valid
└── pets_individuals_02.owl      ← ontologi dengan pelanggaran axiom
```

---

## 3. Konsep: TBox vs ABox

Dalam OWL/Description Logic, sebuah ontologi terdiri dari dua lapisan:

### TBox (Terminological Box) — "Skema/Aturan"

TBox berisi definisi konsep dan aturan yang berlaku secara umum. Ini setara dengan DDL (Data Definition Language) di database relasional.

Contoh TBox dari file `.owl`:

```turtle
# Definisi class dan hierarki
:Kucing    rdfs:subClassOf :PetAnimal .
:PetAnimal rdfs:subClassOf :Animal .
:WildAnimal rdfs:subClassOf :Animal .

# Aturan disjoint — PetAnimal tidak bisa sekaligus WildAnimal
:PetAnimal owl:disjointWith :WildAnimal .

# Definisi property
:hasPet rdfs:domain :PetOwner ;
        rdfs:range  :PetAnimal ;
        rdfs:subPropertyOf :owns .

# Definisi ekuivalen (primitive class dengan syarat)
:OwnsPetAnimal owl:equivalentClass [
    owl:onProperty :owns ;
    owl:someValuesFrom :PetAnimal
] .
```

### ABox (Assertional Box) — "Data/Individu"

ABox berisi pernyataan tentang individu konkret. Ini setara dengan DML (Data Manipulation Language) — baris data yang dimasukkan.

Contoh ABox dari file `.owl`:

```turtle
# Individu dengan tipe eksplisit
:Tom    rdf:type :Kucing .
:Simba  rdf:type :WildAnimal .

# Individu tanpa tipe eksplisit (tipe akan diinfer oleh reasoner)
:Budi   :hasPet :Tweety .
:Dani   :owns   :Tom .
:Tweety rdf:type owl:NamedIndividual .   ← tidak ada tipe kelas
```

### Hubungan TBox dan ABox

```
TBox (aturan)          ABox (data)
─────────────          ───────────
Kucing ⊆ PetAnimal  +  Tom ∈ Kucing
                       ─────────────────────────
                 ↓ reasoner menginfer:
                       Tom ∈ PetAnimal  ✅ (baru, tidak ditulis eksplisit)
```

---

## 4. Isi Ontologi (dari file .owl)

Kedua file `.owl` menggunakan format **Turtle (.ttl)** — keduanya memiliki TBox yang **identik**. Perbedaannya hanya di ABox (individu).

### TBox (sama di kedua file)

**Hierarki Class:**
```
owl:Thing
├── Animal
│   ├── PetAnimal          (disjoint dengan WildAnimal)
│   │   ├── Anjing
│   │   └── Kucing
│   └── WildAnimal
└── PetOwner
    └── OwnsPetAnimal      (≡ owns some PetAnimal)
```

**Object Properties:**
```
owns      → superPropertyOf hasPet
hasPet    → domain: PetOwner, range: PetAnimal
            subPropertyOf: owns
```

**Axiom Kunci:**
```
PetAnimal disjointWith WildAnimal
OwnsPetAnimal ≡ (owns some PetAnimal)
```

### ABox — `pets_individuals_01.owl` (Valid)

| Individu | Dideklarasikan | Diinfer Reasoner |
|---|---|---|
| Budi | `hasPet Tweety` | `PetOwner`, `OwnsPetAnimal` |
| Tweety | *(tidak ada tipe)* | `PetAnimal` |
| Tom | `rdf:type Kucing` | `PetAnimal`, `Animal` |
| Dani | `owns Tom` | `PetOwner`, `OwnsPetAnimal` |

### ABox — `pets_individuals_02.owl` (Inkonsisten)

Sama seperti di atas, ditambah:

| Individu | Dideklarasikan | Masalah |
|---|---|---|
| Simba | `rdf:type WildAnimal` | Diinfer juga sebagai `PetAnimal` via `hasPet` → **kontradiksi** |
| Endang | `hasPet Simba` | Memicu inferensi Simba ∈ PetAnimal |

---

## 5. Alur Program Langkah per Langkah

### Langkah 0 — Reset Awal (sekali, di `main()`)

```python
reset_all_owl_data(session)
```

Menghapus semua node Neo4j yang memiliki properti `source` diawali `'owl'`. Ini hanya dijalankan **sekali** di awal, bukan di tiap demo — supaya data dari Case 1 (valid) tetap ada di Neo4j saat Case 2 dijalankan, sehingga keduanya bisa dibandingkan.

---

### Langkah 1 — Load Ontologi (`load_ontology`)

```python
onto = load_ontology(owl_path)
```

Program membaca file `.owl` dan memuatnya ke memori via `owlready2`.

Karena file menggunakan format **Turtle**, program mendeteksinya terlebih dahulu dengan memeriksa tanda seperti `@prefix`. Jika Turtle terdeteksi, file dikonversi dulu ke **RDF/XML** via `rdflib` karena `owlready2` hanya menerima RDF/XML secara native.

```
File .owl (Turtle)
       │
       ▼
   rdflib parse
       │
       ▼
  RDF/XML (buffer)
       │
       ▼
  owlready2 load
       │
       ▼
  onto (di memori)
  ├── TBox: classes, properties, axioms
  └── ABox: individuals
```

Output di terminal:
```
▶  Membaca file: pets_individuals_01.owl
       Classes     : ['Animal', 'Anjing', 'Kucing', 'OwnsPetAnimal', 'PetAnimal', 'PetOwner', 'WildAnimal']
       Obj Props   : ['hasPet', 'owns']
       Individuals : ['Budi', 'Dani', 'Tom', 'Tweety']
```

---

### Langkah 2 — Jalankan Reasoner (`run_reasoner`)

```python
is_consistent, reason = run_reasoner(onto)
```

Ini equivalen dengan menekan **"Start Reasoner"** di Protégé.

```python
sync_reasoner_hermit(infer_property_values=True)
```

Parameter `infer_property_values=True` memungkinkan reasoner menginfer tipe dari nilai property — misalnya, karena `range(hasPet) = PetAnimal`, maka objek dari `hasPet` otomatis diinfer sebagai `PetAnimal`.

**Jika konsisten** → lanjut ke Langkah 3  
**Jika inkonsisten** → `InconsistentOntologyError` dilempar → program mencetak penjelasan → **berhenti, Neo4j tidak disentuh**

---

### Langkah 3 — Ekstrak Data Post-Reasoning (`extract_graph_data`)

```python
data = extract_graph_data(onto)
```

Setelah reasoner berjalan, `ind.INDIRECT_is_a` sudah berisi **semua tipe** — baik yang ditulis eksplisit maupun yang diinfer. `INDIRECT_is_a` juga menyertakan superclass secara transitif (closure penuh).

Contoh untuk Tom:
```python
# Sebelum reasoning:
Tom.is_a = [Kucing]           # hanya yang ditulis eksplisit

# Setelah reasoning:
Tom.INDIRECT_is_a = [Kucing, PetAnimal, Animal]
#                           ↑ diinfer    ↑ diinfer
```

Hasil ekstraksi:
```python
nodes = [
    {"uri": "http://example.org/Budi",   "name": "Budi",   "labels": ["PetOwner", "OwnsPetAnimal"]},
    {"uri": "http://example.org/Tweety", "name": "Tweety", "labels": ["PetAnimal"]},
    {"uri": "http://example.org/Tom",    "name": "Tom",    "labels": ["Kucing", "PetAnimal", "Animal"]},
    {"uri": "http://example.org/Dani",   "name": "Dani",   "labels": ["PetOwner", "OwnsPetAnimal"]},
]

relationships = [
    {"subject": "Budi", "predicate": "hasPet", "object": "Tweety"},
    {"subject": "Dani", "predicate": "owns",   "object": "Tom"},
]
```

---

### Langkah 4 — Simpan ke Neo4j

Program memanggil tiga fungsi penyimpanan, masing-masing menerima `source_tag` sebagai parameter:

#### `save_nodes(session, nodes, source_tag)`

Membuat node dengan multi-label sesuai tipe yang diinfer.

Cypher yang dieksekusi untuk Budi:
```cypher
MERGE (n:PetOwner:OwnsPetAnimal {uri: 'http://example.org/Budi', source: 'owl_valid'})
SET n.name = 'Budi'
```

Cypher untuk Tom:
```cypher
MERGE (n:Kucing:PetAnimal:Animal {uri: 'http://example.org/Tom', source: 'owl_valid'})
SET n.name = 'Tom'
```

#### `save_relationships(session, relationships, source_tag)`

Membuat relasi antar node. Hanya menghubungkan node dengan `source_tag` yang sama.

```cypher
MATCH (a {name: 'Budi', source: 'owl_valid'})
MATCH (b {name: 'Tweety', source: 'owl_valid'})
MERGE (a)-[r:hasPet]->(b)
SET r.source = 'owl_valid'
```

#### `save_class_hierarchy(session, onto, source_tag)`

Menyimpan hierarki class sebagai node `:OWLClass` dengan relasi `:SCO` (Subclass Of). Ini merepresentasikan TBox di Neo4j untuk keperluan visualisasi.

```cypher
MERGE (c:OWLClass {name: 'Kucing', source: 'owl_valid'})

MATCH (child:OWLClass  {name: 'Kucing',    source: 'owl_valid'})
MATCH (parent:OWLClass {name: 'PetAnimal', source: 'owl_valid'})
MERGE (child)-[:SCO]->(parent)
```

---

### Langkah 5 — Perbandingan Akhir (`query_comparison`)

Dipanggil setelah kedua demo selesai. Menampilkan:
1. Semua node dari Case 1 yang berhasil tersimpan
2. Konfirmasi bahwa Endang dan Simba **tidak ada** di Neo4j

```
📋 Semua node yang BERHASIL tersimpan (owl_valid):
       Budi       → ['PetOwner', 'OwnsPetAnimal']
       Dani       → ['PetOwner', 'OwnsPetAnimal']
       Tom        → ['Kucing', 'PetAnimal', 'Animal']
       Tweety     → ['PetAnimal']

📋 Konfirmasi: Endang & Simba TIDAK tersimpan:
  ✅  Endang dan Simba tidak ada di Neo4j. Pipeline berjalan benar.
```

---

## 6. Istilah Teknis

| Istilah | Penjelasan |
|---|---|
| **OWL** | Web Ontology Language — bahasa standar W3C untuk membuat ontologi |
| **Turtle (.ttl)** | Format serialisasi RDF yang ringkas dan mudah dibaca manusia (`@prefix`, `:Class`) |
| **RDF/XML** | Format serialisasi RDF berbasis XML — format default yang dihasilkan Protégé |
| **RDF** | Resource Description Framework — model data berbasis triple (subjek, predikat, objek) |
| **Triple** | Satu pernyataan RDF, misal: `Tom rdf:type Kucing` |
| **owlready2** | Library Python untuk load dan manipulasi ontologi OWL |
| **rdflib** | Library Python untuk parse berbagai format RDF (Turtle, RDF/XML, N3, dll.) |
| **HermiT** | Reasoner OWL DL berbasis Description Logic — berjalan via Java |
| **TBox** | Terminological Box — bagian ontologi yang berisi definisi class, property, dan axiom |
| **ABox** | Assertional Box — bagian ontologi yang berisi pernyataan tentang individu konkret |
| **Inferensi** | Proses reasoner "menemukan" fakta baru yang tidak ditulis eksplisit |
| **Konsistensi** | Kondisi di mana tidak ada individu yang melanggar axiom di TBox |
| **Axiom** | Pernyataan yang selalu dianggap benar di dalam ontologi (misal: `disjointWith`) |
| **Disjoint** | Dua class yang tidak boleh memiliki anggota yang sama |
| **Equivalent Class** | Definisi class yang menyatakan syarat keanggotaan secara ekuivalen |
| **SCO** | Subclass Of — relasi hierarki antar class |
| **INDIRECT_is_a** | Atribut owlready2 — semua tipe individu termasuk yang diinfer dan superclass transitif |
| **source_tag** | Properti yang ditambahkan ke setiap node Neo4j untuk membedakan asal data |
| **Multi-label** | Fitur Neo4j di mana satu node bisa memiliki lebih dari satu label sekaligus |
| **MERGE** | Cypher command — buat node/relasi jika belum ada, tidak duplikat |
| **bolt://** | Protokol koneksi native Neo4j (lebih cepat dari HTTP) |

---

## 7. Case 1 — Ontologi Valid (`pets_individuals_01.owl`)

### Individu di file (ABox eksplisit)

```turtle
:Budi   rdf:type owl:NamedIndividual ; :hasPet :Tweety .
:Dani   rdf:type owl:NamedIndividual ; :owns   :Tom .
:Tom    rdf:type owl:NamedIndividual , :Kucing .
:Tweety rdf:type owl:NamedIndividual .
```

Perhatikan: Budi, Dani, dan Tweety **tidak memiliki tipe class eksplisit**. Tipe mereka akan ditemukan oleh reasoner.

### Proses Inferensi

```
Axiom di TBox:
  range(hasPet)    = PetAnimal
  hasPet           subPropertyOf owns
  OwnsPetAnimal    ≡ (owns some PetAnimal)
  OwnsPetAnimal    subClassOf PetOwner
  Kucing           subClassOf PetAnimal
  PetAnimal        subClassOf Animal

Fakta di ABox:
  Budi  hasPet  Tweety
  Dani  owns    Tom
  Tom   ∈ Kucing

Inferensi reasoner:
  Tweety ∈ PetAnimal       (karena range hasPet = PetAnimal)
  Tom    ∈ PetAnimal       (karena Kucing ⊆ PetAnimal)
  Tom    ∈ Animal          (karena PetAnimal ⊆ Animal)
  Budi   ∈ OwnsPetAnimal   (karena Budi owns Tweety, Tweety ∈ PetAnimal)
  Budi   ∈ PetOwner        (karena OwnsPetAnimal ⊆ PetOwner)
  Dani   ∈ OwnsPetAnimal   (karena Dani owns Tom, Tom ∈ PetAnimal)
  Dani   ∈ PetOwner        (karena OwnsPetAnimal ⊆ PetOwner)
```

### Hasil di Neo4j

```
Node:
  (:PetOwner:OwnsPetAnimal  {name: 'Budi',   source: 'owl_valid'})
  (:PetAnimal               {name: 'Tweety', source: 'owl_valid'})
  (:Kucing:PetAnimal:Animal  {name: 'Tom',    source: 'owl_valid'})
  (:PetOwner:OwnsPetAnimal  {name: 'Dani',   source: 'owl_valid'})

Relasi:
  (Budi)-[:hasPet]->(Tweety)
  (Dani)-[:owns]->(Tom)

Class hierarchy (TBox):
  (:OWLClass {name:'Kucing'})-[:SCO]->(:OWLClass {name:'PetAnimal'})
  (:OWLClass {name:'PetAnimal'})-[:SCO]->(:OWLClass {name:'Animal'})
  (:OWLClass {name:'Anjing'})-[:SCO]->(:OWLClass {name:'PetAnimal'})
  (:OWLClass {name:'WildAnimal'})-[:SCO]->(:OWLClass {name:'Animal'})
  (:OWLClass {name:'OwnsPetAnimal'})-[:SCO]->(:OWLClass {name:'PetOwner'})
```

---

## 8. Case 2 — Ontologi Inkonsisten (`pets_individuals_02.owl`)

### Tambahan individu di file

```turtle
:Simba  rdf:type owl:NamedIndividual , :WildAnimal .
:Endang rdf:type owl:NamedIndividual ; :hasPet :Simba .
```

### Rantai Kontradiksi

```
Langkah 1 — Fakta eksplisit:
  Simba  ∈ WildAnimal          (dideklarasikan)
  Endang hasPet Simba          (dideklarasikan)

Langkah 2 — Inferensi dari axiom:
  range(hasPet) = PetAnimal
  → Simba HARUS ∈ PetAnimal    (diinfer)

Langkah 3 — Pengecekan disjoint:
  PetAnimal disjointWith WildAnimal
  → Simba ∈ PetAnimal ∩ WildAnimal
  → PetAnimal ∩ WildAnimal = ∅  (dari axiom disjoint)
  → KONTRADIKSI ❌

Hasil:
  OwlReadyInconsistentOntologyError dilempar
  Pipeline berhenti
  Neo4j tidak disentuh
```

### Output Terminal

```
╔════════════════════════════════════════════════════════════╗
║  DEMO 2 (Inkonsisten ❌): pets_individuals_02.owl          ║
╚════════════════════════════════════════════════════════════╝
  ▶  Membaca file: pets_individuals_02.owl
  ▶  Menjalankan HermiT reasoner...
  ❌  Reasoner mendeteksi INKONSISTENSI!
  ❌  Data TIDAK disimpan ke Neo4j.

  Penjelasan kenapa inkonsisten:
  ┌─────────────────────────────────────────────────────┐
  │  Endang hasPet Simba                                │
  │    → range(hasPet) = PetAnimal                     │
  │    → Simba HARUS bertipe PetAnimal (inferensi)      │
  │                                                     │
  │  Simba rdf:type WildAnimal  (dideklarasikan)        │
  │                                                     │
  │  PetAnimal  disjointWith  WildAnimal  (axiom)       │
  │    → Simba ∈ PetAnimal ∩ WildAnimal = ∅            │
  │    → KONTRADIKSI! Reasoner berhenti.                │
  └─────────────────────────────────────────────────────┘
```

---

## 9. Apa yang Tersimpan di Neo4j

### Yang DISIMPAN

| Kategori | Bentuk di Neo4j | Fungsi |
|---|---|---|
| **ABox — Individu** | Node dengan label dari tipe inferred | Data utama |
| **ABox — Relasi** | Relationship antar node | Data utama |
| **TBox — Hierarki class** | `(:OWLClass)-[:SCO]->(:OWLClass)` | Visualisasi skema |

### Yang TIDAK DISIMPAN (tetap di memori OWL)

| Kategori | Contoh | Alasan tidak disimpan |
|---|---|---|
| **Domain/Range axiom** | `range(hasPet) = PetAnimal` | Sudah "dieksekusi" reasoner, hasilnya yang disimpan |
| **Disjoint axiom** | `PetAnimal disjointWith WildAnimal` | Dipakai sebagai constraint, bukan data |
| **Equivalent class** | `OwnsPetAnimal ≡ owns some PetAnimal` | Hasilnya (label inferred) yang disimpan |

Prinsipnya: **axiom dipakai reasoner untuk menghasilkan dan memvalidasi data — hasilnya yang masuk Neo4j, bukan axiom-nya sendiri**.

---

## 10. Query Eksplorasi di Neo4j Browser

Setelah script selesai dijalankan, berikut query yang bisa digunakan:

```cypher
-- Lihat semua data valid beserta relasi
MATCH (n {source: 'owl_valid'})-[r]->(m)
RETURN n, r, m

-- Lihat hanya individu (bukan class hierarchy)
MATCH (n {source: 'owl_valid'})
WHERE NOT n:OWLClass
RETURN n

-- Siapa saja PetOwner?
MATCH (n:PetOwner {source: 'owl_valid'})
RETURN n.name AS nama

-- Apa saja hewan peliharaan?
MATCH (n:PetAnimal {source: 'owl_valid'})
RETURN n.name AS nama

-- Siapa memiliki hewan apa?
MATCH (pemilik {source: 'owl_valid'})-[:hasPet]->(hewan)
RETURN pemilik.name AS pemilik, hewan.name AS hewan

-- Lihat class hierarchy (TBox)
MATCH (child:OWLClass {source: 'owl_valid'})-[:SCO]->(parent:OWLClass)
RETURN child.name AS subclass, parent.name AS superclass

-- Konfirmasi Endang & Simba tidak ada
MATCH (n) WHERE n.name IN ['Endang', 'Simba']
RETURN n
```

---

## 11. Desain Keputusan: Kenapa Axiom Tidak Disimpan ke Neo4j

Neo4j adalah **property graph database** — ia tidak memiliki mesin untuk mengeksekusi OWL axiom. Kalau axiom `disjointWith` disimpan sebagai node/relasi biasa di Neo4j, Neo4j tidak akan otomatis memblokir data yang melanggarnya.

Oleh karena itu, pembagian tugas dirancang sebagai berikut:

```
┌─────────────────────────────────────────────────────────┐
│ OWL + owlready2         │ Menyimpan axiom di memori     │
│ HermiT Reasoner         │ Mengeksekusi axiom:           │
│                         │   - inferensi tipe baru       │
│                         │   - cek konsistensi           │
│ Neo4j                   │ Menyimpan hasil akhir yang    │
│                         │   sudah bersih + diperkaya    │
└─────────────────────────────────────────────────────────┘
```

**Ontologi berperan sebagai validator di hulu** — bukan di Neo4j itu sendiri. Neo4j hanya menerima data yang sudah lolos dan sudah diperkaya oleh reasoner.

Ini adalah konsep yang ingin disampaikan ke mahasiswa: bahwa ontologi bisa berperan lebih dari sekadar dokumentasi — ia bisa menjadi **penjaga gerbang (gatekeeper)** untuk sistem penyimpanan data.