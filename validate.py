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
#   3. Copy-paste this script into the panel and run it.
#   4. Review the output in the Macro Panel's log for detailed validation insights.
#
# Note: This script only performs checks and reports on issues without modifying the font data.

font = Glyphs.font
if font is None:
    print("No font open. Please open a font in Glyphs and try again.")
else:
    master = font.selectedFontMaster  # current master to check
    masterID = master.id

    # Counters for summary
    count_small_segments = 0
    count_suspicious_lengths = 0
    count_close_nodes = 0
    count_collinear = 0
    count_open_paths = 0
    count_isolated = 0

    # Store issues for each glyph: a list of strings (each issue description)
    issues_by_glyph = {}

    # Helper function to format coordinates nicely (drop .0 trailing, use int if possible)
    def fmt_coord(x):
        # Use int if it's effectively an integer
        if abs(x - round(x)) < 0.001:
            x = int(round(x))
        else:
            x = round(x, 2)
        return x

    # Iterate over all glyphs in font
    for glyph in font.glyphs:
        layer = glyph.layers[masterID]
        glyph_name = glyph.name
        issues = []  # collect issues for this glyph

        # Skip glyphs that are non-exporting? (Not specified, so we include all glyphs)
        # Perform checks:

        # (a) Small segments check
        for path in layer.paths:
            for segment in path.segments:  # iterate through segments (line or curve)
                # Bounding box of segment
                seg_bounds = segment.bounds
                seg_w = seg_bounds.size.width
                seg_h = seg_bounds.size.height
                if (seg_w >= 1 and seg_w <= 9) or (seg_h >= 1 and seg_h <= 9):
                    # Coordinates of segment endpoints for reporting
                    try:
                        start_pt = segment.firstPoint()
                        end_pt = segment.lastPoint()
                    except Exception as e:
                        start_pt = None
                        end_pt = None
                    if start_pt is not None and end_pt is not None:
                        x1, y1 = fmt_coord(start_pt.x), fmt_coord(start_pt.y)
                        x2, y2 = fmt_coord(end_pt.x), fmt_coord(end_pt.y)
                        issues.append(f"Small segment from ({x1}, {y1}) to ({x2}, {y2}) " +
                                      f"[bbox {seg_w}×{seg_h}]")
                    else:
                        issues.append(f"Small segment [bbox {(seg_w)}×{(seg_h)}]")
                    count_small_segments += 1

        # (b) Specific suspicious segment lengths check
        target_lengths = [100, 110, 140, 150]
        for path in layer.paths:
            for segment in path.segments:
                seg_length = segment.length()  # geometric length of the segment
                if seg_length is None:
                    continue  # in case segment length couldn't be calculated (e.g., degenerate segment)
                # Check against each target length
                for target in target_lengths:
                    diff = abs(seg_length - target)
                    if 0 < diff <= 3:
                        # Near a target length but not exactly
                        # Round the length for reporting
                        L = round(seg_length, 1)
                        try:
                            start_pt = segment.firstPoint()
                            end_pt = segment.lastPoint()
                        except Exception as e:
                            start_pt = None
                            end_pt = None
                        if start_pt is not None and end_pt is not None:
                            x1, y1 = fmt_coord(start_pt.x), fmt_coord(start_pt.y)
                            x2, y2 = fmt_coord(end_pt.x), fmt_coord(end_pt.y)
                            issues.append(f"Segment at ({x1}, {y1}) length ~{L} (near {target})")
                        else:
                            issues.append(f"Segment length ~{L} (near {target})")
                        count_suspicious_lengths += 1
                        # No need to check other target lengths for this segment (avoid duplicate reporting)
                        break

        # (c) Very close nodes check (on-curve nodes only)
        # Collect all on-curve node coordinates
        oncurve_points = []
        for path in layer.paths:
            for node in path.nodes:
                if node.type != "offcurve":
                    oncurve_points.append((node.x, node.y))
        # Compare each pair (i<j) for distance
        # We use a simple brute force as number of nodes is usually manageable
        n_points = len(oncurve_points)
        for i in range(n_points):
            (x1, y1) = oncurve_points[i]
            for j in range(i+1, n_points):
                (x2, y2) = oncurve_points[j]
                dx = x2 - x1
                dy = y2 - y1
                dist_sq = dx*dx + dy*dy
                if dist_sq < (9 ** 2):  # distance < 9
                    dist = (dist_sq ** 0.5)
                    dist_val = round(dist, 1)
                    x1f, y1f = fmt_coord(x1), fmt_coord(y1)
                    x2f, y2f = fmt_coord(x2), fmt_coord(y2)
                    issues.append(f"Nodes at ({x1f}, {y1f}) and ({x2f}, {y2f}) very close (dist={dist_val})")
                    count_close_nodes += 1

        # (d) Collinear triple (extra node) check
        for path in layer.paths:
            # Get list of on-curve nodes in order
            oncurve_nodes = [node for node in path.nodes if node.type != "offcurve"]
            m = len(oncurve_nodes)
            if m < 3:
                continue
            # If path is closed, the sequence wraps, so handle circular triples
            # We'll iterate indices such that we cover triples (i, i+1, i+2) mod m
            end_index = m if not path.closed else m  # for closed, also consider wrapping triple
            for i in range(m):
                if i+2 >= m:
                    if path.closed:
                        # wrap around for last triples in closed path
                        A = oncurve_nodes[i]
                        B = oncurve_nodes[(i+1) % m]
                        C = oncurve_nodes[(i+2) % m]
                    else:
                        # open path, no wrap beyond end
                        break
                else:
                    A = oncurve_nodes[i]
                    B = oncurve_nodes[i+1]
                    C = oncurve_nodes[i+2]
                # Check if A-B and B-C are both straight line segments (no offcurve between)
                # In Glyphs, if there were off-curve points, B would still appear in oncurve list, 
                # but the presence of off-curves doesn’t affect collinearity of on-curves themselves.
                # So we just check collinearity of coordinates:
                Ax, Ay = A.x, A.y
                Bx, By = B.x, B.y
                Cx, Cy = C.x, C.y
                # Compute cross product of AB and BC vectors to test collinearity
                # (A, B, C collinear if (Bx-Ax)*(Cy-By) == (By-Ay)*(Cx-Bx))
                if abs((Bx - Ax) * (Cy - By) - (By - Ay) * (Cx - Bx)) < 1e-6:
                    # Found collinear triple
                    xB, yB = fmt_coord(Bx), fmt_coord(By)
                    issues.append(f"Extra node at ({xB}, {yB}) (collinear with neighbors)")
                    count_collinear += 1
            # End for path

        # (e) Open path check
        for path in layer.paths:
            if not path.closed:
                num_nodes = len(path.nodes)
                if num_nodes == 0:
                    continue  # skip empty path (shouldn't happen)
                if num_nodes == 1:
                    # single node path will be handled as isolated node below, skip here
                    continue
                # Path has 2 or more nodes and is not closed
                # Identify endpoints (first and last on-curve nodes in the path)
                # Note: In Glyphs, for an open path, the nodes list starts at one end and ends at the other.
                first_node = path.nodes[0]
                last_node = path.nodes[-1]
                # If last node is offcurve, find last oncurve by going backwards
                if last_node and last_node.type == "offcurve":
                    # traverse backwards until oncurve found
                    for node in reversed(path.nodes):
                        if node.type != "offcurve":
                            last_node = node
                            break
                # If first node is offcurve (shouldn't happen in a valid open path structure, open must start with line node as per API docs)
                if first_node and first_node.type == "offcurve":
                    for node in path.nodes:
                        if node.type != "offcurve":
                            first_node = node
                            break
                if first_node and abs(first_node.x) > 1e18:
                    try:
                        first_node = path.segments[0].firstPoint()
                    except Exception as e:
                        first_node = None
                if last_node and abs(last_node.x) > 1e18:
                    try:
                        last_node = path.segments[-1].lastPoint()
                    except Exception as e:
                        last_node = None
                if first_node is None or last_node is None:
                    continue
                fx, fy = fmt_coord(first_node.x), fmt_coord(first_node.y)
                lx, ly = fmt_coord(last_node.x), fmt_coord(last_node.y)
                issues.append(f"Open path (endpoints at ({fx}, {fy}) and ({lx}, {ly}))")
                count_open_paths += 1

        # (f) Isolated single-node path check
        for path in layer.paths:
            if len(path.nodes) == 1:
                node = path.nodes[0]
                x, y = fmt_coord(node.x), fmt_coord(node.y)
                issues.append(f"Isolated node at ({x}, {y})")
                count_isolated += 1

        # (g) Anchors check
        for anchor in layer.anchors:
            ax, ay = fmt_coord(anchor.position.x), fmt_coord(anchor.position.y)
            aname = anchor.name or "(unnamed)"
            issues.append(f"Anchor '{aname}' at ({ax}, {ay})")
            count_isolated += 1  # count anchors as part of isolated points category

        # If no issues found, mark OK; otherwise store issues
        if len(issues) == 0:
            issues_by_glyph[glyph_name] = ["OK"]
        else:
            issues_by_glyph[glyph_name] = issues

    # After scanning all glyphs, print the summary and details:

    # Summary output
    print('////////////////////////////////////////////////////////////////////////////////')
    print('////////////////////////////////////////////////////////////////////////////////')
    print('////////////////////////////////////////////////////////////////////////////////')
    print("Summary of Issues:")
    print(f"  Small segments (<=10 units): {count_small_segments}")
    print(f"  Near specific length segments (~100/110/140/150±3): {count_suspicious_lengths}")
    print(f"  Very close nodes (<9 units apart): {count_close_nodes}")
    print(f"  Collinear extra points: {count_collinear}")
    print(f"  Open paths: {count_open_paths}")
    print(f"  Isolated points or anchors: {count_isolated}")
    print("")  # blank line

    # Detailed per-glyph report
    for glyph in font.glyphs:
        glyph_name = glyph.name
        issues = issues_by_glyph.get(glyph_name, [])
        if not issues:
            # In case glyph had no issues, it was marked OK
            issues = ["OK"]
        # Print glyph name and its issues
        if len(issues) == 1 and issues[0] == "OK":
            print(f"{glyph_name}: OK")
        else:
            print(f"{glyph_name}:")
            for issue in issues:
                print(f"  - {issue}")
    print("")  # blank line

    # Group glyphs by drawn outline width
    width_to_glyphs = {}
    for glyph in font.glyphs:
        layer = glyph.layers[masterID]
        # Calculate outline (bounding box) width
        if layer.bounds is None:
            drawn_width = 0  # no outline
        else:
            drawn_width = int(round(layer.bounds.size.width))  # round to nearest integer unit
        width_to_glyphs.setdefault(drawn_width, []).append(glyph.name)
    # Sort widths and print groups
    print("Outline Width Groups (width: glyphs):")
    for width in sorted(width_to_glyphs.keys()):
        names = ", ".join(sorted(width_to_glyphs[width]))
        print(f"  {width}: {names}")