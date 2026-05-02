## Persiapan sebelum demo

### 1. Python dependencies
```bash
pip install owlready2 neo4j
```

### 2. Java (wajib untuk HermiT reasoner)
```bash
# Cek apakah Java sudah ada
java -version

# Jika belum: install JRE 11 atau 17
# Ubuntu/Debian:
sudo apt install default-jre

# Windows: download dari https://adoptium.net/
```

### 3. Neo4j
Gunakan salah satu:
- **Neo4j Desktop** (recommended untuk demo lokal): https://neo4j.com/download/
- **Docker**:
  ```bash
  docker run \
    --name neo4j-demo \
    -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/password \
    neo4j:5
  ```

### 4. Plugin neosemantics (n10s) — opsional
Dibutuhkan jika ingin import OWL langsung via Cypher `n10s.rdf.import.fetch`.
Untuk demo ini, script Python sudah menangani ekstraksi via owlready2.

Jika ingin install:
1. Buka Neo4j Desktop → Plugin → Install neosemantics
2. Atau download dari: https://neo4j.com/labs/neosemantics/

### 5. Konfigurasi di script
Edit bagian atas `demo_pets_ontology.py`:
```python
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "password"   # sesuaikan
```

### 6. Jalankan demo
```bash
# Letakkan semua file di folder yang sama:
# - demo_pets_ontology.py
# - pets_individuals_01.owl
# - pets_individuals_02.owl

python demo_pets_ontology.py
```

### 7. Verifikasi di Neo4j Browser
Buka http://localhost:7474 lalu jalankan:

```cypher
// Lihat semua node
MATCH (n) RETURN n LIMIT 50

// Siapa saja PetOwner?
MATCH (n:PetOwner) RETURN n.name

// Apa saja hewan peliharaan?
MATCH (n:PetAnimal) RETURN n.name

// Lihat semua relasi
MATCH (a)-[r]->(b) 
WHERE NOT a:OWLClass AND NOT b:OWLClass
RETURN a.name, type(r), b.name

// Hierarki class
MATCH (a:OWLClass)-[:SCO]->(b:OWLClass) 
RETURN a.name, b.name
```

### Output yang diharapkan

**Setelah demo Case 1 (pets_individuals_01.owl):**
- Budi: label :PetOwner :OwnsPetAnimal (diinfer)
- Tweety: label :PetAnimal (diinfer — tidak ada tipe eksplisit di .owl!)
- Tom: label :Kucing :PetAnimal :Animal
- Dani: label :PetOwner :OwnsPetAnimal (diinfer)
- Relasi: (Budi)-[:hasPet]->(Tweety), (Dani)-[:owns]->(Tom)

**Demo Case 2 (pets_individuals_02.owl):**
- Script mendeteksi InconsistentOntologyError
- Neo4j TIDAK disentuh sama sekali
- Pesan error menjelaskan kontradiksi Endang-Simba
