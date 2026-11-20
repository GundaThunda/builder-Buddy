"""
Starting minimum passing scores (floors) per material type, on the 1-100 quality scale.

A material scoring below its floor fails the "not marketably different" match
(website_match.compare). Floors are a proposal awaiting the owner's approval.

Each entry records the standard it is anchored to. The score numbers are a mapping from
those standards onto the 1-100 scale and are NOT values stated by any standard.

Types with no floor (absent here) fail closed in website_match.compare.
"""

# type -> (floor, anchor). `anchor` names the standard or the reason there is none.
FLOORS = {
    # Hardwood. NHLA #1 Common yields 66 2/3-83 1/3% clear wood; visible work stays at or above it.
    "hardwood_visible": (70, "NHLA #1 Common minimum (NHLA Grading Rules Chart)"),
    "hardwood_hidden": (60, "NHLA #2 Common (NHLA Grading Rules Chart)"),

    # Plywood. APA: Exterior bond requires at least C-grade veneer; Exposure 1 is for interior use.
    "plywood_exterior": (60, "APA EW grade glossary: Exterior bond, C minimum"),
    "plywood_interior": (60, "APA EW grade glossary: Exposure 1 bond, C minimum"),

    # Softwood framing. Grades per CWC (Select Structural, No.1-No.3, Stud, Construction, Standard).
    # Structural: No.2 and better for joists, rafters, trusses, lintels. Southern Pine No.2
    # 2x4 design value Fb 1100 psi (SPIB design value tables).
    "softwood_structural": (60, "CWC grades: No.2 and better; SPIB Southern Pine No.2 Fb 1100 psi"),
    # Non-structural framing: plates, sills, blocking (CWC: "where high strength values are not required").
    "softwood_nonstructural": (50, "CWC Construction/Standard grades: plates, sills, blocking"),
    # Economy studs are not stress graded (CWC): deliberately no floor, fails closed.

    # Structural steel. Yield and tensile values from AISC (Fy/Fu in ksi).
    "steel_a992_a572_gr50": (70, "AISC: Fy 50 ksi, Fu 65 ksi"),
    "steel_a36": (60, "AISC: Fy 36 ksi, Fu 58 ksi"),

    # Steel fasteners. SAE grade markings (BoltDepot).
    "steel_fastener_load_bearing": (70, "SAE Grade 5 or better (BoltDepot)"),
    "steel_fastener_nonload": (50, "SAE Grade 2 (BoltDepot)"),

    # Stainless. Grades per BoltDepot.
    "stainless_outdoor": (70, "316: salt water and chlorine environments (BoltDepot)"),
    "stainless_indoor": (60, "18-8 (BoltDepot)"),

    # Aluminum. Aluminum Association Table 12.1, extruded tube (min tensile / min yield, ksi).
    "aluminum_6061_t6": (70, "Aluminum Association T12.1: Fu 38 ksi, Fy 35 ksi"),
    "aluminum_6063_t6": (60, "Aluminum Association T12.1: Fu 30 ksi, Fy 25 ksi"),
    "aluminum_6063_t5": (50, "Aluminum Association T12.1: Fu 22 ksi, Fy 16 ksi"),
}

# Deliberately absent (fail closed):
#   epoxy: ASTM D905 is the closest test method (wood adhesive shear), but it has no
#          passing value and does not name epoxy. Floors need a product-level D905 result.
#   Other metals, finishes, and hardware: no verified source yet.


def floors_by_type() -> dict:
    """Plain {type: floor} mapping in the shape website_match.compare expects."""
    return {t: floor for t, (floor, _anchor) in FLOORS.items()}
