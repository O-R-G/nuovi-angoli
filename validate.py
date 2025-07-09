# Glyphs Font Validation Script
#
# This script is a Glyphs Macro Panel tool designed to validate the outlines
# and structure of glyphs in the current font.
#
# It performs a series of checks across all glyphs, including:
#   (a) Identification of small segments with a bounding box width or height between 1 and 9 units.
#   (b) Detection of segments with lengths near specified target values (e.g., 100, 110, 140, 150 units).
#   (c) Verification of on-curve nodes that are extremely close together.
#   (d) Identification of collinear nodes (extra nodes) where the middle node may not be necessary.
#   (e) Checking open paths to ensure that endpoints are properly defined.
#   (f) Identification of isolated single-node paths and anchors.
#
# The script then prints a summary report detailing:
#   - The count of issues in each category (e.g., small segments, suspicious segment lengths, etc.).
#   - A detailed per-glyph report of all detected issues.
#   - Grouping of glyphs by the drawn outline width.
#
# Importantly, there are some expected false positives. The validation checks are simple, and for shapes
# with multiple paths there may intentionally exist overlapping vertices, or collinear 
# vertices may be necessary to add segment/corner elements (for example, in 8).
# Lengths may be just off specified values when rotated (due to grid rounding).
#
# Usage:
#   1. Open a font in Glyphs.app.
#   2. Open the Macro Panel.

#   4. Review the output in the Macro Panel's log for detailed validation insights.
#
# Note: This script only performs checks and reports on issues without modifying the font data.


# RELAXED mode: when True, smartly remove most false positives (and possibly introduce false negatives).
# For collinear points, tries to avoid when there is a segment between them (e.g. between BC in collinear ABCD)
# For overlapping points, ignore exact overlaps if they a part of two separate paths which exactly share a bounding path (e.g. E, F, T when not baked)
# For anchors, ignore loose named anchors (often used by combining)
# For specific lengths, skip divide and ringcomb, as the rounded distances seem to be calculated differently (and they look good)
# Also for specific lengths, ignore distances that are fractions of a pixel away, as they are likely caused by diagonal lines being quantized to the grid.

RELAXED = True

font = Glyphs.font
if font is None:
    print("No font open. Please open a font in Glyphs and try again.")
else:
    master = font.selectedFontMaster
    masterID = master.id

    # Counters for summary
    count_small_segments = 0
    count_suspicious_lengths = 0
    count_close_nodes = 0
    count_collinear = 0
    count_open_paths = 0
    count_isolated = 0

    issues_by_glyph = {}

    def fmt_coord(x):
        if abs(x - round(x)) < 0.001:
            return int(round(x))
        return round(x, 2)

    def bboxes_touch(bb1, bb2):
        if not bb1 or not bb2:
            return False
        x1_min, y1_min = bb1.origin.x, bb1.origin.y
        x1_max = x1_min + bb1.size.width
        y1_max = y1_min + bb1.size.height
        x2_min, y2_min = bb2.origin.x, bb2.origin.y
        x2_max = x2_min + bb2.size.width
        y2_max = y2_min + bb2.size.height
        flush_x = (x1_max == x2_min or x2_max == x1_min) or (x1_max == x2_max or x1_min == x2_min)
        flush_y = (y1_max == y2_min or y2_max == y1_min) or (y1_max == y2_max or y1_min == y2_min)
        return flush_x or flush_y

    for glyph in font.glyphs:
        layer = glyph.layers[masterID]
        glyph_name = glyph.name
        issues = []

        # (a) Small segments
        for path in layer.paths:
            for segment in path.segments:
                seg_bounds = segment.bounds
                seg_w, seg_h = seg_bounds.size.width, seg_bounds.size.height
                if (1 <= seg_w <= 9) or (1 <= seg_h <= 9):
                    try:
                        sp = segment.firstPoint(); ep = segment.lastPoint()
                    except:
                        sp = ep = None
                    if sp and ep:
                        x1, y1 = fmt_coord(sp.x), fmt_coord(sp.y)
                        x2, y2 = fmt_coord(ep.x), fmt_coord(ep.y)
                        issues.append(f"Small segment from ({x1}, {y1}) to ({x2}, {y2}) [bbox {seg_w}×{seg_h}]")
                    else:
                        issues.append(f"Small segment [bbox {seg_w}×{seg_h}]")
                    count_small_segments += 1

        # (b) Suspicious lengths
        # targets = [65, 85, 100, 110, 140, 150] # for bold masters
        targets = [50, 60, 70, 500, 365, 440, 245, 650] # for roman masters
        for path in layer.paths:
            for segment in path.segments:
                L = segment.length()
                if L is None:
                    continue
                for t in targets:
                    if 1 <= abs(L - t) <= 3:
                        if RELAXED and abs(L-t) < 1:
                            continue
                        if RELAXED and glyph_name.lower() in ["divide", "ringcomb"]: # confusing how it is measuring lengths for these curves. seems fine, but triggers
                            continue
                        Lr = round(L, 1)
                        try:
                            sp, ep = segment.firstPoint(), segment.lastPoint()
                        except:
                            sp = ep = None
                        if sp and ep:
                            x1, y1 = fmt_coord(sp.x), fmt_coord(sp.y)
                            x2, y2 = fmt_coord(ep.x), fmt_coord(ep.y)
                            issues.append(f"Segment at ({x1}, {y1}) length ~{Lr} (near {t})")
                        else:
                            issues.append(f"Segment length ~{Lr} (near {t})")
                        count_suspicious_lengths += 1
                        break

        # (c) Very close nodes
        pts = []
        for path in layer.paths:
            for node in path.nodes:
                if node.type != "offcurve":
                    pts.append((node, path))
        n = len(pts)
        for i in range(n):
            n1, p1 = pts[i]
            x1, y1 = n1.x, n1.y
            for j in range(i+1, n):
                n2, p2 = pts[j]
                x2, y2 = n2.x, n2.y
                dist_sq = (x2 - x1)**2 + (y2 - y1)**2
                if dist_sq < 9**2:
                    if RELAXED and dist_sq == 0 and p1 is not p2 and p1.closed and p2.closed:
                        if bboxes_touch(p1.bounds, p2.bounds):
                            continue
                    d = round(dist_sq**0.5, 1)
                    x1f, y1f = fmt_coord(x1), fmt_coord(y1)
                    x2f, y2f = fmt_coord(x2), fmt_coord(y2)
                    issues.append(f"Nodes at ({x1f}, {y1f}) and ({x2f}, {y2f}) very close (dist={d})")
                    count_close_nodes += 1

        # (d) Collinear triples with segment-component skipping
        for path in layer.paths:
            nodes = path.nodes
            # 1) collect indices of on-curve nodes
            on_indices = [i for i, n in enumerate(nodes) if n.type != "offcurve"]
            m = len(on_indices)
            if m < 3:
                continue
            total = len(nodes)

            # 2) if RELAXED, find all nodes that are part of a segment component hint
            skip_nodes = set()
            if RELAXED:
                for hint in layer.hints:
                    # 19 is the TrueType SEGMENT hint type
                    if hint.type == 19 and hint.name and hint.name.startswith("_segment."):
                        origin = getattr(hint, "originNode", None)
                        if origin:
                            skip_nodes.add(origin)
                        target = getattr(hint, "targetNode", None)
                        if target:
                            skip_nodes.add(target)

            # 3) walk each triple A→B→C (wrap only if path.closed)
            for j in range(m):
                if not path.closed and j > m - 3:
                    break

                iA = on_indices[j]
                iB = on_indices[(j + 1) % m]
                iC = on_indices[(j + 2) % m]
                A, B, C = nodes[iA], nodes[iB], nodes[iC]

                # 4) skip if B or C sits on a segment component
                if RELAXED and (B in skip_nodes or C in skip_nodes):
                    continue

                # 5) enforce literal adjacency (pure two-point lines)
                if iB != (iA + 1) % total or iC != (iB + 1) % total:
                    continue

                # 6) exact collinearity via cross-product
                cross = (B.x - A.x) * (C.y - A.y) - (B.y - A.y) * (C.x - A.x)
                if abs(cross) < 1e-6:
                    xB, yB = fmt_coord(B.x), fmt_coord(B.y)
                    issues.append(f"Extra node at ({xB}, {yB}) (collinear with neighbors)")
                    count_collinear += 1
                    
        # (e) Open path endpoints
        for path in layer.paths:
            if not path.closed:
                cnt = len(path.nodes)
                if cnt <= 1:
                    continue
                first_node = path.nodes[0]
                last_node = path.nodes[-1]
                # guard against None
                if first_node is None or last_node is None:
                    continue
                if first_node.type == "offcurve":
                    for nd in path.nodes:
                        if nd and nd.type != "offcurve":
                            first_node = nd
                            break
                if last_node.type == "offcurve":
                    for nd in reversed(path.nodes):
                        if nd and nd.type != "offcurve":
                            last_node = nd
                            break
                # if still None or offcurve, skip
                if first_node is None or last_node is None:
                    continue
                fx, fy = fmt_coord(first_node.x), fmt_coord(first_node.y)
                lx, ly = fmt_coord(last_node.x), fmt_coord(last_node.y)
                issues.append(f"Open path (endpoints at ({fx}, {fy}) and ({lx}, {ly}))")
                count_open_paths += 1

        # (f) Isolated nodes
        for path in layer.paths:
            if len(path.nodes) == 1:
                nd = path.nodes[0]
                if nd:
                    x, y = fmt_coord(nd.x), fmt_coord(nd.y)
                    issues.append(f"Isolated node at ({x}, {y})")
                    count_isolated += 1

        # (g) Anchors
        for anchor in layer.anchors:
            ax, ay = fmt_coord(anchor.position.x), fmt_coord(anchor.position.y)
            name = anchor.name or "(unnamed)"
            skip = [
                'top','bottom','ogonek','center','topleft','topright',
                '_top','_bottom','origin','start','end','_center',
                '_ogonek','_topleft','_topright','left'
            ]
            if RELAXED and name in skip:
                continue
            issues.append(f"Anchor '{name}' at ({ax}, {ay})")
            count_isolated += 1

        issues_by_glyph[glyph_name] = issues or ["OK"]

    # Print summary
    print('////////////////////////////////////////////////////////////////')
    print('////////////////////////////////////////////////////////////////')
    print('////////////////////////////////////////////////////////////////')
    print("Summary of Issues:")
    print(f"  Small segments (<=10 units): {count_small_segments}")
    print(f"  Near specific length segments (~65/85/100/110/140/150±3): {count_suspicious_lengths}")
    print(f"  Very close nodes (<9 units apart): {count_close_nodes}")
    print(f"  Collinear extra points: {count_collinear}")
    print(f"  Open paths: {count_open_paths}")
    print(f"  Isolated points or anchors: {count_isolated}\n")

    # Detailed per-glyph report
    for glyph in font.glyphs:
        name = glyph.name
        glyph_issues = issues_by_glyph.get(name, ["OK"])
        if glyph_issues == ["OK"]:
            print(f"{name}: OK")
        else:
            print(f"{name}:")
            for issue in glyph_issues:
                print(f"  - {issue}")
    print("")

    # Outline width groups
    width_groups = {}
    for glyph in font.glyphs:
        b = glyph.layers[masterID].bounds
        w = 0 if b is None else int(round(b.size.width))
        width_groups.setdefault(w, []).append(glyph.name)
    print("Outline Width Groups (width: glyphs):")
    for w in sorted(width_groups):
        print(f"  {w}: {', '.join(sorted(width_groups[w]))}")

    # Outline height groups
    height_groups = {}
    for glyph in font.glyphs:
        b = glyph.layers[masterID].bounds
        h = 0 if b is None else int(round(b.size.height))
        height_groups.setdefault(h, []).append(glyph.name)
    print("Outline Height Groups (height: glyphs):")
    for h in sorted(height_groups):
        print(f"  {h}: {', '.join(sorted(height_groups[h]))}")