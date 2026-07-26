"""Generate data/enrichment.json from the live-research pass (Finnrick per-peptide
public data + Peptigrity individual results + kold.us verified Retatrutide COA).

Kept as a generator so the enrichment is reproducible and easy to extend.
Run: python backend/gen_enrichment.py   ->  writes ../data/enrichment.json
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "enrichment.json"
FINN = "Finnrick"

# ---------------------------------------------------------------------------
# 1) Vendor-level corrections (real Finnrick OVERALL rating + totals).
#    Several vendors were previously overstated because a peptide-leaderboard
#    score was mistaken for the overall (Peptide Partners/SRY/Zenith were 91).
#    (name, overall_agg_score, total_tests, pass, fail)
# ---------------------------------------------------------------------------
VENDOR_UPDATES = [
    ("Peptide Sciences", 61, 131, 79, 52),
    ("Paradigm Peptides", 86, 18, 17, 1),
    ("Peptide Partners", 64, 77, 52, 25),        # was 91 (reta-only) -> 64 overall
    ("SRY Labs", 61, 121, 78, 43),               # was 91 -> 61 overall
    ("Zenith Jove Peptide", 77, 59, 51, 8),      # was 91 -> 77 overall
    ("Amino Lair", 87, 18, 17, 1),
    ("SubQ Society", 84, 11, 9, 2),
    ("Chimera Peptides", 86, 20, 19, 1),
    ("Orbitrex Peptides", 84, 30, 25, 5),
    ("Aavant Research", 87, 18, 18, 0),
    ("Inno Peptides", 89, 21, 21, 0),
    ("Marvel Pep", 88, 16, 15, 1),
    ("Retalux", 86, 15, 15, 0),
    ("Kits4less", 85, 7, 7, 0),
    ("BioLongevity Labs", 74, 33, 25, 8),        # was null composite -> 74
    ("Prime Peptides", 55, 19, 7, 12),           # was null -> 55
    ("Guangzhou Jeep Biotechnology (JEEP)", 87, 36, 32, 4),
    ("Wuhan Newtop Biotech", 86, 6, 6, 0),       # was null -> 86
]

# ---------------------------------------------------------------------------
# 2) Finnrick PUBLIC per-peptide rows. Purity/dosage are paywalled, so we store
#    the public per-peptide RATING (0-100) + test count + latest date.
#    (vendor, slug, peptide, rating, tests, date)
# ---------------------------------------------------------------------------
FINN_SLUG = {
    "Peptide Sciences": "peptide-sciences", "Paradigm Peptides": "paradigm-peptide",
    "Peptide Partners": "peptide-partners", "SRY Labs": "sry-labs",
    "Zenith Jove Peptide": "zenith-jove-peptide-zj", "Amino Lair": "amino-lair",
    "SubQ Society": "subq-society", "Chimera Peptides": "chimera-peptides",
    "Orbitrex Peptides": "orbitrex-peptides", "Aavant Research": "aavant-research",
    "Inno Peptides": "inno-peptides", "Marvel Pep": "marvel-pep", "Retalux": "retalux",
    "Kits4less": "kits4less", "BioLongevity Labs": "biolongevity-labs",
    "Prime Peptides": "prime-peptides",
    "Guangzhou Jeep Biotechnology (JEEP)": "guangzhou-jeep-biotechnology-jeep",
    "Wuhan Newtop Biotech": "wuhan-newtop-biotech",
}

# (vendor, peptide, rating, tests, date)
FINN_ROWS = [
    ("Peptide Sciences", "GHK-Cu", 92, 6, None),
    ("Peptide Sciences", "Semaglutide", 81, 15, None),
    ("Peptide Sciences", "PT-141", 79, 6, None),
    ("Peptide Sciences", "Ipamorelin", 78, 9, None),
    ("Peptide Sciences", "Tirzepatide", 68, 17, "2026-07-01"),
    ("Peptide Sciences", "BPC-157", 61, 13, None),
    ("Peptide Sciences", "Retatrutide", 56, 41, "2026-06-17"),
    ("Peptide Sciences", "Melanotan II", 54, 10, None),
    ("Peptide Sciences", "Tesamorelin", 39, 3, "2026-04-28"),
    ("Peptide Sciences", "CJC-1295", 16, 11, "2026-05-06"),
    ("Paradigm Peptides", "Tirzepatide", 88, 10, "2026-01-26"),
    ("Paradigm Peptides", "Retatrutide", 85, 8, "2026-04-30"),
    ("Peptide Partners", "Retatrutide", 91, 23, "2026-06-16"),
    ("Peptide Partners", "Ipamorelin", 83, 7, None),
    ("Peptide Partners", "Tirzepatide", 80, 7, None),
    ("Peptide Partners", "BPC-157", 52, 9, "2026-06-22"),
    ("Peptide Partners", "Tesamorelin", 50, 11, None),
    ("Peptide Partners", "CJC-1295", 37, 9, None),
    ("Peptide Partners", "TB-500", 31, 11, "2026-03-04"),
    ("SRY Labs", "Tirzepatide", 92, 35, "2026-05-06"),
    ("SRY Labs", "Retatrutide", 91, 31, "2026-06-08"),
    ("SRY Labs", "GHK-Cu", 68, 7, None),
    ("SRY Labs", "Semaglutide", 65, 4, None),
    ("SRY Labs", "PT-141", 52, 2, None),
    ("SRY Labs", "Cagrilintide", 50, 8, "2026-05-08"),
    ("SRY Labs", "BPC-157", 43, 7, None),
    ("SRY Labs", "Sermorelin", 40, 3, "2026-03-06"),
    ("SRY Labs", "TB-500", 36, 8, None),
    ("SRY Labs", "Tesamorelin", 32, 12, "2026-03-02"),
    ("SRY Labs", "CJC-1295", 27, 4, None),
    ("Zenith Jove Peptide", "GHK-Cu", 92, 5, None),
    ("Zenith Jove Peptide", "Retatrutide", 91, 21, "2026-07-01"),
    ("Zenith Jove Peptide", "Tirzepatide", 81, 22, "2026-05-05"),
    ("Zenith Jove Peptide", "BPC-157", 65, 7, "2026-06-08"),
    ("Zenith Jove Peptide", "TB-500", 39, 4, "2026-06-08"),
    ("Amino Lair", "Retatrutide", 87, 9, "2026-07-13"),
    ("Amino Lair", "Tirzepatide", 86, 9, "2026-06-06"),
    ("SubQ Society", "GHK-Cu", 91, 3, "2026-03-10"),
    ("SubQ Society", "Retatrutide", 78, 8, "2026-05-08"),
    ("Chimera Peptides", "Retatrutide", 89, 11, "2026-05-25"),
    ("Chimera Peptides", "Tirzepatide", 83, 9, "2026-07-01"),
    ("Orbitrex Peptides", "GHK-Cu", 91, 5, "2026-06-02"),
    ("Orbitrex Peptides", "Retatrutide", 89, 18, "2026-06-12"),
    ("Orbitrex Peptides", "Tirzepatide", 79, 5, None),
    ("Orbitrex Peptides", "PT-141", 70, 2, "2026-07-17"),
    ("Aavant Research", "Tirzepatide", 89, 11, "2026-05-20"),
    ("Aavant Research", "Retatrutide", 85, 7, "2026-03-03"),
    ("Inno Peptides", "GHK-Cu", 92, 4, "2026-05-13"),
    ("Inno Peptides", "Retatrutide", 89, 10, "2026-07-17"),
    ("Inno Peptides", "Tirzepatide", 86, 7, "2026-07-13"),
    ("Marvel Pep", "GHK-Cu", 91, 4, "2026-07-13"),
    ("Marvel Pep", "Retatrutide", 85, 12, "2026-07-13"),
    ("Retalux", "SS-31", 91, 4, "2026-06-16"),
    ("Retalux", "Retatrutide", 86, 7, "2026-07-20"),
    ("Retalux", "Tirzepatide", 83, 4, "2026-06-26"),
    ("Kits4less", "Retatrutide", 85, 7, "2026-03-03"),
    ("BioLongevity Labs", "GHK-Cu", 91, 4, "2025-12-06"),
    ("BioLongevity Labs", "Retatrutide", 80, 11, "2025-07-23"),
    ("BioLongevity Labs", "Ipamorelin", 76, 4, None),
    ("BioLongevity Labs", "PT-141", 71, 3, "2025-08-12"),
    ("BioLongevity Labs", "BPC-157", 47, 11, "2025-11-22"),
    ("Prime Peptides", "Ipamorelin", 78, 5, "2025-06-13"),
    ("Prime Peptides", "GHK-Cu", 69, 5, "2025-07-10"),
    ("Prime Peptides", "BPC-157", 40, 6, "2025-07-10"),
    ("Prime Peptides", "CJC-1295", 29, 3, "2025-07-03"),
    ("Guangzhou Jeep Biotechnology (JEEP)", "GHK-Cu", 92, 5, "2026-07-13"),
    ("Guangzhou Jeep Biotechnology (JEEP)", "Tirzepatide", 87, 15, "2026-07-20"),
    ("Guangzhou Jeep Biotechnology (JEEP)", "Retatrutide", 84, 16, "2026-07-20"),
    ("Wuhan Newtop Biotech", "GHK-Cu", 89, 1, "2026-03-07"),
    ("Wuhan Newtop Biotech", "Retatrutide", 83, 5, "2026-05-08"),
]

# ---------------------------------------------------------------------------
# 3) New vendors surfaced by Peptigrity (with real measured purity).
# ---------------------------------------------------------------------------
NEW_VENDORS = [
    {"name": "Ascend Science", "website": "https://ascend.science", "vendor_type": "consumer",
     "publishes_coa": "yes", "community_score": 0.3,
     "community_notes": "34+ individual third-party HPLC results via Peptigrity (Kovera Labs), consistently 98.5-99.8% across a very broad catalog. Strong testing transparency."},
    {"name": "Modified Aminos", "website": "https://modifiedaminos.shop", "vendor_type": "consumer",
     "publishes_coa": "yes", "community_score": 0.1,
     "community_notes": "Broad catalog third-party tested via Ethos Analytics (Peptigrity), ~99% with endotoxin passes."},
    {"name": "BioPeptiTech", "website": "https://biopeptitech.com", "vendor_type": "consumer",
     "publishes_coa": "yes", "community_score": 0.1,
     "community_notes": "Third-party tested via Accurate Test Lab (Peptigrity); 97-99.9% depending on peptide."},
    {"name": "American Peptides (US)", "website": "https://americanpeptides.us", "vendor_type": "consumer",
     "publishes_coa": "yes", "community_score": None,
     "community_notes": "Third-party results via Bioviridian (Peptigrity) with endotoxin passes."},
]

# Peptigrity measured-purity rows: (vendor, peptide, purity, lab, date, endotoxin_pass)
PG = "Peptigrity"
PEPTIGRITY_ROWS = [
    # Ascend Science (Kovera Labs) — showcase breadth incl. Retatrutide/Semaglutide
    ("Ascend Science", "Semaglutide", 99.66, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Semaglutide", 98.50, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Tesamorelin", 99.63, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Tesamorelin", 99.54, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "CJC-1295", 99.50, "Kovera Labs", "2026-07-09", 1),
    ("Ascend Science", "CJC-1295", 99.42, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "BPC-157", 99.61, "Kovera Labs", "2026-07-09", 1),
    ("Ascend Science", "TB-500", 99.52, "Kovera Labs", "2026-07-09", 1),
    ("Ascend Science", "Ipamorelin", 99.53, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "GHK-Cu", 99.58, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "PT-141", 99.43, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Cagrilintide", 99.64, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "SS-31", 99.77, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Melanotan II", 99.54, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "NAD+", 99.69, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Sermorelin", 99.55, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Epithalon", 99.83, "Kovera Labs", "2026-07-09", None),
    ("Ascend Science", "Thymosin Alpha-1", 99.60, "Kovera Labs", "2026-07-09", None),
    # Modified Aminos (Ethos Analytics) — many at ~99% with endotoxin pass
    ("Modified Aminos", "Tesamorelin", 99.0, "Ethos Analytics", "2026-07-06", 1),
    ("Modified Aminos", "TB-500", 99.0, "Ethos Analytics", "2026-07-06", 1),
    ("Modified Aminos", "SS-31", 99.0, "Ethos Analytics", "2026-07-06", 1),
    ("Modified Aminos", "SEMAX", 99.0, "Ethos Analytics", "2026-07-06", 1),
    ("Modified Aminos", "SELANK", 99.0, "Ethos Analytics", "2026-07-06", 1),
    ("Modified Aminos", "PT-141", 99.0, "Ethos Analytics", "2026-07-06", 1),
    ("Modified Aminos", "MOTS-C", 99.0, "Ethos Analytics", "2026-07-06", 1),
    ("Modified Aminos", "KPV", 99.0, "Ethos Analytics", "2026-07-06", 1),
    # BioPeptiTech (Accurate Test Lab)
    ("BioPeptiTech", "Tirzepatide", 99.50, "Accurate Test Lab", "2026-07-06", None),
    ("BioPeptiTech", "PT-141", 99.92, "Accurate Test Lab", "2026-07-09", None),
    ("BioPeptiTech", "SEMAX", 99.68, "Accurate Test Lab", "2026-07-09", None),
    ("BioPeptiTech", "Thymalin", 99.94, "Accurate Test Lab", "2026-07-06", None),
    ("BioPeptiTech", "DSIP", 97.10, "Accurate Test Lab", "2026-07-09", None),
    # American Peptides (US) (Bioviridian)
    ("American Peptides (US)", "GHK-Cu", 99.80, "Bioviridian", "2026-07-07", 1),
    ("American Peptides (US)", "Retatrutide/Cagrilintide", 99.90, "Bioviridian", "2026-07-07", 1),
    # Felix Chemical Supply (existing) — real Freedom Diagnostics rows
    ("Felix Chemical Supply", "Tesamorelin", 99.86, "Freedom Diagnostics Testing", "2026-04-26", 1),
    ("Felix Chemical Supply", "NAD+", 99.80, "Freedom Diagnostics Testing", "2026-04-26", 1),
    ("Felix Chemical Supply", "GHK-Cu", 99.81, "Freedom Diagnostics Testing", "2026-04-26", 1),
    ("Felix Chemical Supply", "BPC-157", 98.74, "Freedom Diagnostics Testing", "2026-04-26", 1),
]

# ---------------------------------------------------------------------------
# 4) kold.us verified Retatrutide (G3-R lot 1032, Accumark code WYGR-AJDT).
# ---------------------------------------------------------------------------
KOLD_RETA = {
    "vendor_name": "KÖLD (kold.us)", "peptide": "Retatrutide",
    "purity_pct": 99.9, "dosage_accuracy_pct": 103.7, "endotoxin_pass": 1,
    "tests_count": 1, "test_date": "2026-06-16",
    "source_name": "Accumark Labs COA (verified WYGR-AJDT)",
    "source_url": "https://accumarklabs.com/verify?code=WYGR-AJDT",
    "lab_name": "Accumark Labs",
    "notes": "G3-R 10mg lot 1032: HPLC 99.9% (spec >98%), fill 10.37/10mg, endotoxin PASS (<5 EU/mL); sterility PENDING, no heavy metals. Independently verified on Accumark's domain.",
}


def build():
    peptide_tests = []
    for vendor, peptide, rating, tests, date in FINN_ROWS:
        peptide_tests.append({
            "vendor_name": vendor, "peptide": peptide, "peptide_rating": rating,
            "tests_count": tests, "test_date": date, "source_name": FINN,
            "source_url": f"https://www.finnrick.com/vendors/{FINN_SLUG[vendor]}",
        })
    for vendor, peptide, purity, lab, date, endo in PEPTIGRITY_ROWS:
        peptide_tests.append({
            "vendor_name": vendor, "peptide": peptide, "purity_pct": purity,
            "lab_name": lab, "test_date": date, "endotoxin_pass": endo,
            "tests_count": 1, "source_name": PG,
            "source_url": "https://peptigrity.com/lab-tests",
        })
    peptide_tests.append(KOLD_RETA)

    data = {
        "_meta": {"generated": "2026-07-25",
                  "note": "Finnrick per-peptide ratings are public composites (purity paywalled); "
                          "Peptigrity rows are measured HPLC purity; kold row is a verified Accumark COA."},
        "vendor_updates": [
            {"name": n, "agg_score": s, "agg_tests": t, "pass_count": p, "fail_count": f}
            for (n, s, t, p, f) in VENDOR_UPDATES
        ],
        "new_vendors": NEW_VENDORS,
        "peptide_tests": peptide_tests,
    }
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}: {len(data['vendor_updates'])} updates, "
          f"{len(NEW_VENDORS)} new vendors, {len(peptide_tests)} peptide rows")


if __name__ == "__main__":
    build()
