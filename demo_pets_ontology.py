"""
╔══════════════════════════════════════════════════════════════════╗
║  Demo: OWL Ontology → HermiT Reasoner → Neo4j                   ║
║  Studi kasus: Pets Ontology                ║
║                                                                   ║
║  Alur:                                                            ║
║    .owl file → owlready2 load → HermiT reasoner →               ║
║    jika KONSISTEN  → ekstrak individuals + inferred types         ║
║                    → simpan ke Neo4j (source_tag = owl_valid)    ║
║    jika INKONSISTEN → blokir, tidak menyentuh Neo4j              ║
║                                                                   ║
║  Catatan penting:                                                 ║
║    - Clear hanya dilakukan SEKALI di awal main()                 ║
║    - Setiap dataset diberi source_tag berbeda                    ║
║    - Kedua dataset tetap ada di Neo4j untuk dieksplorasi         ║
║                                                                   ║
║  Requirements:                                                    ║
║    pip install owlready2 neo4j                                   ║
║    Java (JRE 8+) — dibutuhkan oleh HermiT reasoner              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import textwrap
import io
from pathlib import Path

import owlready2
from owlready2 import (
    get_ontology,
    sync_reasoner_hermit,
    OwlReadyInconsistentOntologyError as InconsistentOntologyError,
    ThingClass,
    Thing,
)
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable


# ══════════════════════════════════════════════════════════════════
#  KONFIGURASI — sesuaikan dengan environment kamu
# ══════════════════════════════════════════════════════════════════

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "12345678"          # ganti sesuai password Neo4j kamu

# Path ke file OWL (sesuaikan jika file ada di folder lain)
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OWL_VALID   = os.path.join(BASE_DIR, "pets_individuals_01.owl")   # tidak ada pelanggaran
OWL_INVALID = os.path.join(BASE_DIR, "pets_individuals_02.owl")   # ada Endang + Simba


# ══════════════════════════════════════════════════════════════════
#  HELPER: pretty print
# ══════════════════════════════════════════════════════════════════

def header(title: str):
    bar = "═" * 60
    print(f"\n╔{bar}╗")
    print(f"║  {title:<58}║")
    print(f"╚{bar}╝")

def step(msg: str):
    print(f"  ▶  {msg}")

def ok(msg: str):
    print(f"  ✅  {msg}")

def err(msg: str):
    print(f"  ❌  {msg}")

def warn(msg: str):
    print(f"  ⚠️   {msg}")

def info(msg: str):
    print(f"       {msg}")


# ══════════════════════════════════════════════════════════════════
#  TAHAP 1 — Load & Reasoning
# ══════════════════════════════════════════════════════════════════

def load_ontology(owl_path: str):
    """
    Load file .owl ke owlready2.
    Menggunakan owlready2.default_world; ontologi lama dengan IRI
    yang sama akan di-destroy terlebih dahulu agar tidak bercampur.
    """
    step(f"Membaca file: {os.path.basename(owl_path)}")

    # Bersihkan ontologi sebelumnya jika IRI sama (http://example.org/)
    target_iri = "http://example.org/"
    if target_iri in owlready2.default_world.ontologies:
        owlready2.default_world.ontologies[target_iri].destroy()

    onto = get_ontology("http://example.org/")

    # Detect common Turtle/N3 markers and convert to RDF/XML using rdflib
    try:
        with open(owl_path, "r", encoding="utf-8") as fh:
            head = fh.read(2048)
    except UnicodeDecodeError:
        head = ""

    is_turtle = False
    if head:
        if "@prefix" in head or "@base" in head or head.lstrip().startswith("PREFIX") or "[" in head:
            is_turtle = True
    if owl_path.lower().endswith(('.ttl', '.n3')):
        is_turtle = True

    if is_turtle:
        step("Detected Turtle/N3 format — converting to RDF/XML via rdflib...")
        try:
            from rdflib import Graph
        except Exception:
            err("rdflib belum terinstal. Instal dengan: pip install rdflib")
            sys.exit(1)

        g = Graph()
        fmt = "turtle"
        try:
            g.parse(owl_path, format=fmt)
        except Exception:
            g.parse(owl_path)

        xml = g.serialize(format="xml")
        buf = io.BytesIO(xml.encode("utf-8"))
        onto.load(fileobj=buf)
    else:
        with open(owl_path, "rb") as f:
            onto.load(fileobj=f)

    info(f"Classes     : {[c.name for c in onto.classes()]}")
    info(f"Obj Props   : {[p.name for p in onto.object_properties()]}")
    info(f"Individuals : {[i.name for i in onto.individuals()]}")
    return onto


def run_reasoner(onto) -> tuple[bool, str]:
    """
    Jalankan HermiT reasoner via owlready2.
    - infer_property_values=True → reasoner juga menginfer nilai property
      (misalnya: Budi hasPet Tweety → Tweety diinfer sebagai PetAnimal)

    Returns:
        (is_consistent: bool, message: str)
    """
    step("Menjalankan HermiT reasoner...")
    try:
        with onto:
            sync_reasoner_hermit(infer_property_values=True)
        ok("Reasoner selesai — ontologi KONSISTEN")
        return True, "OK"

    except InconsistentOntologyError as exc:
        err("Reasoner mendeteksi INKONSISTENSI!")
        info(str(exc))
        return False, str(exc)


# ══════════════════════════════════════════════════════════════════
#  TAHAP 2 — Ekstrak Data (post-reasoning)
# ══════════════════════════════════════════════════════════════════

def extract_graph_data(onto) -> dict:
    """
    Setelah reasoner berjalan, `ind.is_a` sudah berisi tipe-tipe yang
    DIINFER oleh reasoner (bukan hanya yang ditulis eksplisit di .owl).

    Contoh:
      - Tweety  : tidak ada tipe eksplisit → setelah reasoning: [PetAnimal]
      - Budi    : tidak ada tipe eksplisit → setelah reasoning: [PetOwner, OwnsPetAnimal]
      - Tom     : eksplisit [Kucing]       → setelah reasoning: [Kucing, PetAnimal, Animal]
    """
    step("Mengekstrak individuals + inferred types...")

    nodes = []
    relationships = []

    for ind in onto.individuals():
        labels = []
        for cls in ind.INDIRECT_is_a:
            if isinstance(cls, ThingClass) and cls.name not in ("Thing",):
                labels.append(cls.name)

        nodes.append({
            "uri":    ind.iri,
            "name":   ind.name,
            "labels": labels,
        })

        for prop in onto.object_properties():
            for obj in prop[ind]:
                if isinstance(obj, Thing):
                    relationships.append({
                        "subject":   ind.name,
                        "predicate": prop.name,
                        "object":    obj.name,
                    })

    print()
    for n in nodes:
        info(f"  {n['name']:<10} → labels: {n['labels']}")
    print()
    for r in relationships:
        info(f"  ({r['subject']})-[:{r['predicate']}]->({r['object']})")

    return {"nodes": nodes, "relationships": relationships}


# ══════════════════════════════════════════════════════════════════
#  TAHAP 3 — Simpan ke Neo4j
# ══════════════════════════════════════════════════════════════════

def reset_all_owl_data(session):
    """
    Hapus SEMUA data OWL dari Neo4j.
    Dipanggil SEKALI saja di awal main() untuk reset bersih,
    bukan di tiap demo — supaya data valid dan invalid bisa
    dieksplorasi bersama di Neo4j Browser.
    """
    result = session.run(
        "MATCH (n) WHERE n.source STARTS WITH 'owl' "
        "DETACH DELETE n RETURN count(n) AS deleted"
    )
    count = result.single()["deleted"]
    if count:
        warn(f"Reset awal: {count} node lama dari run sebelumnya dihapus.")
    else:
        info("Neo4j bersih, tidak ada data lama.")


def save_nodes(session, nodes: list, source_tag: str):
    """
    Buat node di Neo4j dengan multi-label + source_tag.

    source_tag membedakan asal data:
      'owl_valid'   → dari pets_individuals_01.owl (lolos reasoner)
      'owl_invalid_attempt' → tidak pernah sampai sini (diblokir)

    Contoh Cypher untuk Budi (source_tag='owl_valid'):
      MERGE (n:PetOwner:OwnsPetAnimal {uri: '...', source: 'owl_valid'})
      SET n.name = 'Budi'
    """
    step(f"Menyimpan nodes ke Neo4j (source={source_tag})...")
    for node in nodes:
        if not node["labels"]:
            label_str = "OWLIndividual"
        else:
            label_str = ":".join(node["labels"])

        cypher = (
            f"MERGE (n:{label_str} {{uri: $uri, source: $source}}) "
            f"SET n.name = $name "
            f"RETURN n.name AS created"
        )
        result = session.run(
            cypher,
            uri=node["uri"],
            name=node["name"],
            source=source_tag,
        )
        record = result.single()
        info(f"  Saved: ({record['created']} :{label_str}) [source={source_tag}]")


def save_relationships(session, relationships: list, source_tag: str):
    """
    Buat relationship di Neo4j berdasarkan object property assertions.
    Hanya menghubungkan node dengan source_tag yang sama.

    Contoh Cypher:
      MATCH (a {name: 'Budi', source: 'owl_valid'})
      MATCH (b {name: 'Tweety', source: 'owl_valid'})
      MERGE (a)-[:hasPet]->(b)
    """
    step(f"Menyimpan relationships ke Neo4j (source={source_tag})...")
    for rel in relationships:
        cypher = (
            f"MATCH (a {{name: $subject, source: $source}}) "
            f"MATCH (b {{name: $object, source: $source}}) "
            f"MERGE (a)-[r:`{rel['predicate']}`]->(b) "
            f"SET r.source = $source "
            f"RETURN type(r) AS rel_type"
        )
        result = session.run(
            cypher,
            subject=rel["subject"],
            object=rel["object"],
            source=source_tag,
        )
        record = result.single()
        if record:
            info(f"  Saved: ({rel['subject']})-[:{record['rel_type']}]->({rel['object']})")
        else:
            warn(
                f"  Relasi gagal: ({rel['subject']})-[:{rel['predicate']}]->"
                f"({rel['object']}) — node tidak ditemukan?"
            )


def save_class_hierarchy(session, onto, source_tag: str):
    """
    Simpan hierarki class sebagai node :OWLClass dengan relasi :SCO
    (Subclass Of). Membantu visualisasi di Neo4j Browser.
    
    Catatan: iterasi semua classes dan ALL parents (termasuk indirect via 
    INDIRECT_is_a untuk capture super-superclasses).
    """
    step(f"Menyimpan class hierarchy (source={source_tag})...")
    
    all_classes = list(onto.classes())
    info(f"Total {len(all_classes)} classes ditemukan di ontologi")
    
    # Langkah 1: Buat semua class nodes
    for cls in all_classes:
        session.run(
            "MERGE (c:OWLClass {name: $name, source: $source})",
            name=cls.name,
            source=source_tag,
        )
        info(f"  ✓ Created :OWLClass {cls.name}")
    
    # Langkah 2: Buat semua SCO relationships
    sco_count = 0
    for cls in all_classes:
        # Gunakan INDIRECT_is_a untuk capture semua ancestors (closure penuh)
        for parent in cls.INDIRECT_is_a:
            if isinstance(parent, ThingClass) and parent.name not in ("Thing",):
                # Hindari duplikasi langsung: hanya buat relasi ke direct parents
                if parent in cls.is_a:
                    session.run(
                        """
                        MATCH (child:OWLClass  {name: $child,  source: $source})
                        MATCH (parent:OWLClass {name: $parent, source: $source})
                        MERGE (child)-[:SCO]->(parent)
                        """,
                        child=cls.name,
                        parent=parent.name,
                        source=source_tag,
                    )
                    info(f"  (:OWLClass {cls.name})-[:SCO]->(:OWLClass {parent.name})")
                    sco_count += 1
    
    info(f"Total {sco_count} SCO relationships dibuat")


def query_demo(session, source_tag: str):
    """
    Jalankan beberapa query untuk verifikasi data yang masuk,
    difilter berdasarkan source_tag.
    """
    queries = [
        (
            "Siapa saja kucing? (:Kucing)",
            "MATCH (n:Kucing {source: $src}) RETURN n.name AS name",
        ),
        (
            "Apa saja hewan peliharaan? (:PetAnimal)",
            "MATCH (n:PetAnimal {source: $src}) RETURN n.name AS name",
        ),
        (
            "Siapa saja PetOwner? (:PetOwner)",
            "MATCH (n:PetOwner {source: $src}) RETURN n.name AS name",
        ),
        (
            "Semua relasi hasPet",
            "MATCH (a {source: $src})-[:hasPet]->(b) "
            "RETURN a.name AS owner, b.name AS pet",
        ),
    ]

    print()
    step(f"Verifikasi query Neo4j (source={source_tag})...")
    print()
    for title, cypher in queries:
        results = session.run(cypher, src=source_tag).data()
        print(f"  📋 {title}")
        if results:
            for row in results:
                print(f"       {row}")
        else:
            print(f"       (tidak ada hasil)")
        print()


def query_comparison(session):
    """
    Query perbandingan akhir — ditampilkan setelah KEDUA demo selesai.
    Menunjukkan perbedaan isi Neo4j antara data valid vs yang diblokir.
    """
    header("PERBANDINGAN AKHIR: Data di Neo4j")

    # Semua node yang masuk (valid)
    print("\n  📋 Semua node yang BERHASIL tersimpan (owl_valid):")
    results = session.run(
        "MATCH (n) WHERE n.source = 'owl_valid' AND NOT n:OWLClass "
        "RETURN n.name AS name, labels(n) AS labels "
        "ORDER BY n.name"
    ).data()
    for row in results:
        print(f"       {row['name']:<10} → {row['labels']}")

    # Konfirmasi Endang & Simba tidak ada
    print("\n  📋 Konfirmasi: Endang & Simba TIDAK tersimpan:")
    results = session.run(
        "MATCH (n) WHERE n.name IN ['Endang', 'Simba'] RETURN n.name AS name"
    ).data()
    if results:
        for row in results:
            warn(f"  Ditemukan: {row['name']} — periksa kembali!")
    else:
        ok("Endang dan Simba tidak ada di Neo4j. Pipeline berjalan benar.")

    print()
    print("  💡 Query eksplorasi di Neo4j Browser:")
    print("       // Lihat semua data valid + relasi")
    print("       MATCH (n {source: 'owl_valid'})-[r]->(m)")
    print("       RETURN n, r, m")
    print()
    print("       // Konfirmasi Endang & Simba tidak ada")
    print("       MATCH (n) WHERE n.name IN ['Endang', 'Simba'] RETURN n")
    print()


# ══════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════

def demo_run(owl_path: str, driver, label: str, source_tag: str):
    """
    Satu siklus demo lengkap untuk satu file OWL.

    Args:
        owl_path   : path ke file .owl
        driver     : Neo4j driver (sudah terkoneksi)
        label      : label untuk display (e.g. "1 (Valid ✅)")
        source_tag : tag yang disimpan ke property 'source' di Neo4j
                     sehingga data dari tiap demo bisa dibedakan
    """
    header(f"DEMO {label}: {os.path.basename(owl_path)}")

    # ── Tahap 1: Load ──
    onto = load_ontology(owl_path)

    # ── Tahap 2: Reasoning ──
    is_consistent, reason = run_reasoner(onto)

    # ── Gerbang: blokir jika tidak konsisten ──
    if not is_consistent:
        err("Data TIDAK disimpan ke Neo4j.")
        print()
        print(textwrap.dedent(f"""
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
        """))
        return   # ← keluar tanpa menyentuh Neo4j

    # ── Tahap 3: Ekstrak data (post-reasoning) ──
    data = extract_graph_data(onto)

    # ── Tahap 4: Simpan ke Neo4j ──
    #    Tidak ada clear di sini — data tetap ada untuk dieksplorasi
    step("Menghubungkan ke Neo4j...")
    with driver.session() as session:
        save_nodes(session, data["nodes"], source_tag)
        save_relationships(session, data["relationships"], source_tag)
        save_class_hierarchy(session, onto, source_tag)
        query_demo(session, source_tag)

    ok(
        f"Selesai! {len(data['nodes'])} nodes + "
        f"{len(data['relationships'])} relationships tersimpan "
        f"di Neo4j dengan source='{source_tag}'."
    )


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    print("\n" + "═" * 62)
    print("  Demo: OWL Ontology → HermiT Reasoner → Neo4j")
    print("  Versi: pets ontology (Bu Ade Hodijah, 2026)")
    print("═" * 62)

    # Cek file OWL ada
    for path in [OWL_VALID, OWL_INVALID]:
        if not os.path.exists(path):
            err(f"File tidak ditemukan: {path}")
            err("Pastikan .owl files ada di folder yang sama dengan script ini.")
            sys.exit(1)

    # Koneksi ke Neo4j
    step("Menghubungkan ke Neo4j...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        ok(f"Terhubung ke Neo4j di {NEO4J_URI}")
    except ServiceUnavailable:
        err(f"Tidak bisa terhubung ke Neo4j di {NEO4J_URI}")
        err("Pastikan Neo4j berjalan dan kredensial benar.")
        sys.exit(1)

    try:
        # ── Reset SEKALI di awal — bersihkan data dari run sebelumnya ──
        #    Setelah ini, TIDAK ada lagi clear di tengah demo.
        #    Tujuan: data valid dan invalid tetap sama-sama ada di Neo4j
        #    sehingga bisa dieksplorasi & dibandingkan di Neo4j Browser.
        header("RESET AWAL — Membersihkan data dari run sebelumnya")
        with driver.session() as session:
            reset_all_owl_data(session)

        # ── CASE 1: Ontologi valid — harus masuk Neo4j ──
        demo_run(
            OWL_VALID,
            driver,
            label="1 (Valid ✅)",
            source_tag="owl_valid",
        )

        # ── CASE 2: Ontologi inkonsisten — harus diblokir ──
        #    source_tag 'owl_invalid_attempt' tidak akan pernah tersimpan
        #    karena pipeline keluar lebih awal saat inkonsistensi terdeteksi
        demo_run(
            OWL_INVALID,
            driver,
            label="2 (Inkonsisten ❌)",
            source_tag="owl_invalid_attempt",
        )

        # ── Perbandingan akhir ──
        with driver.session() as session:
            query_comparison(session)

    finally:
        driver.close()
        print("\n" + "═" * 62)
        print("  Neo4j driver ditutup. Demo selesai.")
        print("═" * 62 + "\n")


if __name__ == "__main__":
    main()