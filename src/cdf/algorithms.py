"""
Geometry basics -- reusable Rhino.Geometry functions for Grasshopper.

Adding a new function with Copilot
-----------------------------------
1. Open this file and select this chat model, then ask Copilot something like:
   "Add a function here, all in Rhino geometry, that builds a <your shape/idea>.
   Follow the same style as create_cone / create_fractal_tree (defaults for
   optional inputs, a docstring listing params, return a Rhino.Geometry object)."
2. Once the function is added, ask Copilot:
   "Give me the Python code to use this function in a Grasshopper GHPython 3
   component, importing it from computational_design_and_fabrication."
3. Copy the snippet Copilot gives you into a GHPython component, wire up the
   inputs as sliders/panels, and set the output variable (e.g. `a`).
"""

import math
import Rhino.Geometry as rg
import random

def fibonacci_row_lengths(base_chain=8, rows_up=3, rows_down=3):
    """Return the stitch count for each row in a Fibonacci-shaped sequence.

    Params:
        base_chain (int): Starting stitch count, rounded up to a Fibonacci
            number if needed. Default 8.
        rows_up (int): Number of rows to increase from the base. Default 3.
        rows_down (int): Number of rows to decrease after the increase,
            capped at rows_up. Default 3.

    Returns:
        list of int: stitches per row, e.g. [8, 13, 21, 34, 21, 13, 8].
    """
    fibonacci = [1, 2]
    while fibonacci[-1] < base_chain:
        fibonacci.append(fibonacci[-1] + fibonacci[-2])

    base_index = next(
        index for index, count in enumerate(fibonacci) if count >= base_chain
    )
    peak_index = base_index + rows_up
    while len(fibonacci) <= peak_index:
        fibonacci.append(fibonacci[-1] + fibonacci[-2])

    row_lengths = fibonacci[base_index : peak_index + 1]
    for offset in range(1, min(rows_down, rows_up) + 1):
        row_lengths.append(fibonacci[peak_index - offset])

    return row_lengths


def even_stitch_pattern(current, target):
    """Spread increases or decreases evenly along a row.

    Returns a list with one number per stitch of the current row: how many
    stitches it produces in the next row.
        2 = increase (two new stitches into this stitch)
        1 = normal stitch
        0 = second stitch of a decrease pair (the first one of the pair
            has a 1, together the two stitches make one new stitch)
    The numbers always add up to target.
    """
    pattern = [1] * current
    diff = target - current

    if diff > current:
        raise ValueError("Cannot more than double a row.")
    if -diff * 2 > current:
        raise ValueError("Cannot decrease more than half a row.")

    if diff > 0:
        for k in range(diff):
            pattern[int((k + 0.5) * current / diff)] = 2
    elif diff < 0:
        pairs = -diff
        for k in range(pairs):
            start = int(k * current / pairs)
            pattern[start + 1] = 0
    return pattern


def place_fibonacci_stitches(base_chain=8, rows_up=3, rows_down=3,
                             stitch_width=1.0, stitch_height=2.0):
    """Place every stitch of the Fibonacci up-and-down piece as a point.

    Rows hang downwards (negative Z). Each stitch sits below its parent;
    stitches of an increase share the parent's width, a decrease sits
    between its two parents. Nothing is relaxed yet, so rows with more
    stitches are still squeezed into the width of the row above.

    Returns:
        rows    -- list of rows, each a list of Rhino.Geometry.Point3d
        parents -- same shape; for each stitch the list of parent indices
                   in the row above (1 parent, or 2 for a decrease)
    """
    lengths = fibonacci_row_lengths(base_chain, rows_up, rows_down)

    # row 0: the chain, a straight line of stitches
    rows = [[rg.Point3d(i * stitch_width, 0.0, 0.0) for i in range(lengths[0])]]
    parents = [[[] for _ in range(lengths[0])]]

    for r in range(1, len(lengths)):
        prev = rows[r - 1]
        pattern = even_stitch_pattern(len(prev), lengths[r])
        z = -r * stitch_height
        new_row, new_parents = [], []

        for i, count in enumerate(pattern):
            p = prev[i]
            if count == 2:  # increase: two stitches into one
                for dx in (-0.25, 0.25):
                    new_row.append(rg.Point3d(p.X + dx * stitch_width, 0.0, z))
                    new_parents.append([i])
            elif count == 1 and i + 1 < len(pattern) and pattern[i + 1] == 0:
                q = prev[i + 1]  # decrease: two stitches into one
                new_row.append(rg.Point3d((p.X + q.X) / 2.0, 0.0, z))
                new_parents.append([i, i + 1])
            elif count == 1:  # normal stitch
                new_row.append(rg.Point3d(p.X, 0.0, z))
                new_parents.append([i])
            # count == 0: already used by the decrease before it

        rows.append(new_row)
        parents.append(new_parents)

    return rows, parents


def place_fibonacci_ring(base_chain=8, rows_up=3, rows_down=3,
                         stitch_width=1.0, stitch_height=2.0):
    """Place every stitch of the Fibonacci up-and-down piece worked in rounds.

    Same recipe as place_fibonacci_stitches, but every row is a closed ring:
    the starting chain is joined into a ring (the opening, at z = 0) and the
    rounds hang below it. Growing rounds flare out, shrinking rounds close the
    piece again, like a vase or a pod. Nothing is relaxed yet.

    Returns:
        rows    -- list of rounds, each a list of Rhino.Geometry.Point3d
        parents -- same shape; for each stitch the list of parent indices
                   in the round above (1 parent, or 2 for a decrease)
    """
    lengths = fibonacci_row_lengths(base_chain, rows_up, rows_down)

    def point(angle, radius, z):
        return rg.Point3d(radius * math.cos(angle), radius * math.sin(angle), z)

    # round 0: the chain joined into a ring, one stitch_width per stitch
    n0 = lengths[0]
    radius0 = n0 * stitch_width / (2.0 * math.pi)
    angles = [[2.0 * math.pi * i / n0 for i in range(n0)]]
    radii = [[radius0] * n0]
    rows = [[point(a, radius0, 0.0) for a in angles[0]]]
    parents = [[[] for _ in range(n0)]]

    for r in range(1, len(lengths)):
        prev_n = lengths[r - 1]
        step = 2.0 * math.pi / prev_n
        pattern = even_stitch_pattern(prev_n, lengths[r])
        z = -r * stitch_height
        new_angles, new_radii, new_parents = [], [], []

        for i, count in enumerate(pattern):
            a, rad = angles[r - 1][i], radii[r - 1][i]
            if count == 2:  # increase: two stitches into one
                for da in (-0.25, 0.25):
                    new_angles.append(a + da * step)
                    new_radii.append(rad)
                    new_parents.append([i])
            elif count == 1 and i + 1 < prev_n and pattern[i + 1] == 0:
                # decrease: two stitches into one, sits between its parents
                new_angles.append(a + 0.5 * step)
                new_radii.append(rad)
                new_parents.append([i, i + 1])
            elif count == 1:  # normal stitch
                new_angles.append(a)
                new_radii.append(rad)
                new_parents.append([i])
            # count == 0: already used by the decrease before it

        angles.append(new_angles)
        radii.append(new_radii)
        rows.append([point(a, rad, z) for a, rad in zip(new_angles, new_radii)])
        parents.append(new_parents)

    return rows, parents


def relax_fibonacci_stitches(rows, parents, stitch_width=1.0, stitch_height=2.0,
                             iterations=200, jitter=0.3, smoothing=0.1,
                             gravity=0.0, seed=1, closed=False, collision=0.0):
    """Let the stitches settle like springs, so the piece ruffles.

    Takes the output of place_fibonacci_stitches. The chain (row 0) is the
    hanging line and stays fixed. Every stitch is pulled towards the right
    distance from its parent (stitch_height) and from its neighbours in the
    row (stitch_width). Rows with more stitches than room have to buckle.

    Params:
        rows, parents: from place_fibonacci_stitches.
        iterations (int): Relaxation steps. 0 = no change. Default 200.
        jitter (float): Random nudge (in stitch widths) that lets the flat
            layout buckle. Default 0.3.
        smoothing (float): Fabric stiffness, 0 to about 0.3. Pulls each
            stitch towards the middle of its neighbours so creases become
            smoother folds. Higher values squeeze stitches a bit more.
            Default 0.1.
        gravity (float): Pull downwards per step, 0 to about 0.1. Makes the
            piece hang longer. Default 0.
        seed (int): Same seed gives the same shape, another seed gives another
            fold pattern. Default 1.
        closed (bool): True when every row is a closed ring (use with
            place_fibonacci_ring), so the last stitch of a row is also a
            neighbour of the first. Default False.
        collision (float): Thickness of the fabric in stitch widths, 0 to
            about 1. Stitches that are not worked into each other cannot get
            closer than this, so folds press against each other instead of
            passing through each other. 0 switches it off. Default 0.

    Returns:
        List of rows, each a list of Rhino.Geometry.Point3d.
    """
    rng = random.Random(seed)

    # flatten: one entry per stitch, remember where each row starts
    points, fixed, start = [], [], []
    for r, row in enumerate(rows):
        start.append(len(points))
        for p in row:
            points.append([p.X, p.Y, p.Z])
            fixed.append(r == 0)  # the chain is the hanging line, it stays put

    # springs: (i, j, rest_length, stiffness)
    springs = []
    neighbours = [[] for _ in points]  # for smoothing: who touches whom
    for r in range(1, len(rows)):
        for k, plist in enumerate(parents[r]):
            child = start[r] + k
            for pi in plist:  # post: stitch to the stitch it is worked into
                parent = start[r - 1] + pi
                springs.append((parent, child, stitch_height, 1.0))
                neighbours[child].append(parent)
                neighbours[parent].append(child)
    for r in range(1, len(rows)):
        n = len(rows[r])
        pairs = n if closed else n - 1  # a closed ring also joins last to first
        for k in range(pairs):  # neighbours in a row, one stitch wide
            a, b = start[r] + k, start[r] + (k + 1) % n
            springs.append((a, b, stitch_width, 1.0))
            neighbours[a].append(b)
            neighbours[b].append(a)
        skips = (n if n > 4 else 0) if closed else n - 2
        for k in range(skips):  # weak spring over one stitch keeps it smooth
            springs.append((start[r] + k, start[r] + (k + 2) % n, 2.0 * stitch_width, 0.15))

    # stitches that are joined by a spring never collide with each other
    linked = set((min(i, j), max(i, j)) for i, j, _, _ in springs)
    collision_distance = collision * stitch_width

    # small random nudge so the flat layout can buckle
    for i, p in enumerate(points):
        if not fixed[i]:
            p[0] += rng.uniform(-jitter, jitter) * stitch_width
            p[1] += rng.uniform(-jitter, jitter) * stitch_width
            p[2] += rng.uniform(-jitter, jitter) * stitch_width

    for _ in range(iterations):
        for i, j, rest, stiffness in springs:
            a, b = points[i], points[j]
            dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length < 1e-9:
                continue
            move = 0.5 * stiffness * (length - rest) / length
            if fixed[i] and fixed[j]:
                continue
            if fixed[i]:
                f_a, f_b = 0.0, 2.0
            elif fixed[j]:
                f_a, f_b = 2.0, 0.0
            else:
                f_a, f_b = 1.0, 1.0
            a[0] += dx * move * f_a; a[1] += dy * move * f_a; a[2] += dz * move * f_a
            b[0] -= dx * move * f_b; b[1] -= dy * move * f_b; b[2] -= dz * move * f_b

        # collision: stitches that are not worked into each other keep their
        # distance, so the fabric cannot pass through itself
        if collision_distance > 0.0:
            cell = collision_distance
            grid = {}
            for index, p in enumerate(points):
                key = (int(math.floor(p[0] / cell)),
                       int(math.floor(p[1] / cell)),
                       int(math.floor(p[2] / cell)))
                grid.setdefault(key, []).append(index)
            for (cx, cy, cz), members in grid.items():
                for ox in (-1, 0, 1):
                    for oy in (-1, 0, 1):
                        for oz in (-1, 0, 1):
                            others = grid.get((cx + ox, cy + oy, cz + oz))
                            if not others:
                                continue
                            for i in members:
                                for j in others:
                                    if j <= i or (fixed[i] and fixed[j]):
                                        continue
                                    if (i, j) in linked:
                                        continue
                                    a, b = points[i], points[j]
                                    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                                    d2 = dx * dx + dy * dy + dz * dz
                                    if d2 >= cell * cell or d2 < 1e-12:
                                        continue
                                    dist = math.sqrt(d2)
                                    push = 0.5 * (cell - dist) / dist
                                    if fixed[i]:
                                        f_a, f_b = 0.0, 2.0
                                    elif fixed[j]:
                                        f_a, f_b = 2.0, 0.0
                                    else:
                                        f_a, f_b = 1.0, 1.0
                                    a[0] -= dx * push * f_a; a[1] -= dy * push * f_a; a[2] -= dz * push * f_a
                                    b[0] += dx * push * f_b; b[1] += dy * push * f_b; b[2] += dz * push * f_b

        # gravity: every free stitch is pulled down a little each step
        if gravity > 0.0:
            for i, p in enumerate(points):
                if not fixed[i]:
                    p[2] -= gravity

        # fabric stiffness: pull every stitch a little towards the middle of
        # its neighbours, so sharp creases turn into smoother folds
        if smoothing > 0.0:
            moved = [p[:] for p in points]
            for i, p in enumerate(points):
                if fixed[i] or not neighbours[i]:
                    continue
                for axis in range(3):
                    mean = sum(points[j][axis] for j in neighbours[i]) / len(neighbours[i])
                    moved[i][axis] = p[axis] + smoothing * (mean - p[axis])
            points[:] = moved

    return [[rg.Point3d(*points[start[r] + k]) for k in range(len(row))]
            for r, row in enumerate(rows)]


def loop_subdivide(vertices, faces, levels=1):
    """Smooth a triangle mesh with Loop subdivision (every triangle becomes 4).

    Params:
        vertices (list): (x, y, z) tuples.
        faces (list): (a, b, c) vertex indices.
        levels (int): Number of subdivision rounds. Default 1.

    Returns:
        (vertices, faces) of the smoothed mesh.
    """
    for _ in range(levels):
        count = len(vertices)
        edge_opposite = {}
        for a, b, c in faces:
            for u, v, w in ((a, b, c), (b, c, a), (c, a, b)):
                edge_opposite.setdefault((min(u, v), max(u, v)), []).append(w)
        neighbours = [set() for _ in range(count)]
        boundary = [[] for _ in range(count)]
        for (u, v), opposite in edge_opposite.items():
            neighbours[u].add(v)
            neighbours[v].add(u)
            if len(opposite) == 1:  # open edge of the mesh
                boundary[u].append(v)
                boundary[v].append(u)

        # moved old vertices
        new_vertices = []
        for i in range(count):
            v = vertices[i]
            if len(boundary[i]) >= 2:  # on the open edge: stay on the edge
                b1, b2 = vertices[boundary[i][0]], vertices[boundary[i][1]]
                new_vertices.append(tuple(
                    0.75 * v[k] + 0.125 * (b1[k] + b2[k]) for k in range(3)))
                continue
            n = len(neighbours[i])
            if n < 3:
                new_vertices.append(v)
                continue
            beta = (0.625 - (0.375 + 0.25 * math.cos(2.0 * math.pi / n)) ** 2) / n
            total = [sum(vertices[j][k] for j in neighbours[i]) for k in range(3)]
            new_vertices.append(tuple(
                (1.0 - n * beta) * v[k] + beta * total[k] for k in range(3)))

        # one new vertex in the middle of every edge
        middle = {}
        for (u, v), opposite in edge_opposite.items():
            if len(opposite) == 2:
                c, d = opposite
                p = tuple(0.375 * (vertices[u][k] + vertices[v][k])
                          + 0.125 * (vertices[c][k] + vertices[d][k]) for k in range(3))
            else:
                p = tuple(0.5 * (vertices[u][k] + vertices[v][k]) for k in range(3))
            middle[(u, v)] = len(new_vertices)
            new_vertices.append(p)

        new_faces = []
        for a, b, c in faces:
            ab = middle[(min(a, b), max(a, b))]
            bc = middle[(min(b, c), max(b, c))]
            ca = middle[(min(c, a), max(c, a))]
            new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        vertices, faces = new_vertices, new_faces
    return vertices, faces


def build_stitch_mesh(rows, parents, closed=False, cap=False, smooth=0):
    """Connect the stitch points into a triangle mesh (the crochet fabric).

    Every pair of neighbouring stitches in a row is joined to the stitch(es)
    they were worked into in the row above. A decrease stitch, which is worked
    into two stitches, also gets the triangle between its two parents.

    Params:
        closed (bool): True when every row is a closed ring (the last stitch
            is joined to the first). Default False.
        cap (bool): Only with closed rows: pull the last round shut with a
            fan of triangles to one centre point. Default False.
        smooth (int): Rounds of Loop subdivision, 0 to 2. Each round makes the
            surface smoother and 4 times as heavy. Default 0.

    Returns:
        Rhino.Geometry.Mesh
    """
    vertices, faces, start = [], [], []
    for row in rows:
        start.append(len(vertices))
        for p in row:
            vertices.append((p.X, p.Y, p.Z))

    for r in range(1, len(rows)):
        n = len(rows[r])
        for k in range(n):
            child = start[r] + k
            plist = parents[r][k]
            # a decrease stitch is worked into two stitches: close the triangle
            if len(plist) == 2:
                faces.append((start[r - 1] + plist[0], child, start[r - 1] + plist[1]))
            if k < n - 1 or closed:
                nxt = (k + 1) % n
                c1 = start[r] + nxt
                p0 = start[r - 1] + plist[-1]
                p1 = start[r - 1] + parents[r][nxt][0]
                faces.append((p0, child, c1))
                if p1 != p0:
                    faces.append((p0, c1, p1))

    if closed and cap and len(rows) > 1:
        last = rows[-1]
        centre = len(vertices)
        vertices.append((sum(p.X for p in last) / len(last),
                         sum(p.Y for p in last) / len(last),
                         sum(p.Z for p in last) / len(last)))
        for k in range(len(last)):
            faces.append((start[-1] + k, centre, start[-1] + (k + 1) % len(last)))

    if smooth > 0:
        vertices, faces = loop_subdivide(vertices, faces, min(smooth, 2))

    mesh = rg.Mesh()
    for x, y, z in vertices:
        mesh.Vertices.Add(x, y, z)
    for a, b, c in faces:
        mesh.Faces.AddFace(a, b, c)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def write_crochet_pattern(base_chain=8, rows_up=4, rows_down=4, stitch_type=1):
    """Write the crochet pattern of the Fibonacci pod as pseudocode.

    The text follows the style of the course README (PROCEDURE, CALL, FOR,
    // comments), so it can be crocheted stitch by stitch. It uses the same
    row lengths and the same evenly spread increases and decreases as the
    model.

    Params:
        base_chain (int): Foundation chain, rounded up to a Fibonacci number.
        rows_up (int): Rounds that grow. Default 4.
        rows_down (int): Rounds that shrink again. Default 4.
        stitch_type (int): 1 = single, 2 = double, 3 = treble crochet.

    Returns:
        str: the pattern, one line per row of text.
    """
    lengths = fibonacci_row_lengths(base_chain, rows_up, rows_down)
    name = {1: "single", 2: "double", 3: "treble"}[stitch_type]
    work = name + "_crochet_to_stitch()"
    together = name + "_crochet_two_together()"
    down = min(rows_down, rows_up)

    lines = []
    add = lines.append
    add("PROCEDURE CrochetFibonacciPod(base_chain_stitch_count=%d, rounds_up=%d, "
        "rounds_down=%d, stitch=%s)" % (lengths[0], rows_up, down, name))
    add("")
    add("    // Fibonacci rule: every round adds as many stitches as the round before")
    add("    // it had. After the biggest round the rounds shrink again.")
    add("    // Stitches per round: " + ", ".join(str(n) for n in lengths))
    add("")
    add("    // 1. Start and make a base line")
    add("    current_layer = 0")
    add("    CALL make_a_starting_slipknot() // go to video for instructions")
    add("")
    add("    FOR index = 1 TO base_chain_stitch_count")
    add("        CALL make_a_chain_stitch() // go to video for instructions")
    add("    END FOR")
    add("")
    add("    // 2. Join to the first stitch to make a ring")
    add("    CALL make_a_slipstitch_to_first_chain() // go to video for instructions")
    add("    current_stitches_in_round = %d" % lengths[0])
    add("")
    add("    // 3. Fibonacci rounds in spiral, work into the stitches of the round before")

    for r in range(1, len(lengths)):
        current, target = lengths[r - 1], lengths[r]
        pattern = even_stitch_pattern(current, target)
        add("")
        if target > current:
            where = [i + 1 for i, c in enumerate(pattern) if c == 2]
            add("    // Round %d: %d -> %d stitches (%d increases)"
                % (r, current, target, len(where)))
            add("    increase_in_stitches = [" + ", ".join(str(s) for s in where) + "]")
            add("    FOR s = 1 TO current_stitches_in_round")
            add("        IF s IN increase_in_stitches")
            add("            FOR k = 1 TO 2")
            add("                CALL %s // go to video for instructions" % work)
            add("            END FOR")
            add("        ELSE")
            add("            CALL %s // go to video for instructions" % work)
            add("        END IF")
            add("    END FOR")
        else:
            pairs = [(i + 1, i + 2) for i, c in enumerate(pattern)
                     if c == 1 and i + 1 < current and pattern[i + 1] == 0]
            add("    // Round %d: %d -> %d stitches (%d decreases)"
                % (r, current, target, len(pairs)))
            add("    decrease_over_stitches = ["
                + ", ".join("(%d, %d)" % p for p in pairs) + "]")
            add("    s = 1")
            add("    WHILE s <= current_stitches_in_round")
            add("        IF (s, s + 1) IN decrease_over_stitches")
            add("            CALL %s // two stitches into one, not in the videos" % together)
            add("            s = s + 2")
            add("        ELSE")
            add("            CALL %s // go to video for instructions" % work)
            add("            s = s + 1")
            add("        END IF")
            add("    END WHILE")
        add("    current_stitches_in_round = %d" % target)
        add("    current_layer = current_layer + 1")

    add("")
    if down > 0:
        add("    // 4. Close the pod: pull the yarn through the last round and tighten")
    else:
        add("    // 4. Leave the last round open and fasten off")
    add("    CALL finish_pattern() // go to video for instructions")
    add("")
    add("END PROCEDURE")
    return "\n".join(lines)

def create_fractal_tree(
    base_point=None,
    base_plane=None,
    length=10.0,
    angle=25.0,
    length_factor=0.7,
    depth=8,
    branch_count=2,
):
    """
    Build a fractal (recursively branching) tree as a list of line segments.

    base_point    : Rhino.Geometry.Point3d -- start point of the trunk
    base_plane    : Rhino.Geometry.Plane   -- plane whose YAxis is the trunk
                     direction and ZAxis is the branching rotation axis
    length        : float -- trunk length
    angle         : float -- angle in degrees between sibling branches
    length_factor : float -- length multiplier applied at each new generation
    depth         : int   -- number of recursive branching generations
    branch_count  : int   -- number of branches spawned at each node

    Returns a list of Rhino.Geometry.Line.
    """
    if base_point is None:
        base_point = rg.Point3d(0, 0, 0)
    if base_plane is None:
        base_plane = rg.Plane.WorldXY

    lines = []

    def _grow(start, direction, branch_length, remaining_depth):
        if remaining_depth <= 0 or branch_length <= 1e-6:
            return

        end = start + direction * branch_length
        lines.append(rg.Line(start, end))

        if branch_count <= 1:
            offsets = [0.0]
        else:
            span = angle * (branch_count - 1)
            offsets = [-span / 2.0 + i * angle for i in range(branch_count)]

        for offset in offsets:
            rotated_direction = rg.Vector3d(direction)
            rotated_direction.Rotate(math.radians(offset), base_plane.ZAxis)
            _grow(end, rotated_direction, branch_length * length_factor, remaining_depth - 1)

    _grow(base_point, base_plane.YAxis, length, depth)

    return lines


def create_crochet_pseudosphere(
    rounds=4,
    first_round=12,
    increase=3,
    base_chain=4,
    stitch_width=1.0,
    stitch_height=2.0,
    iterations=150,
    seed=1,
    max_stitches=1500,
):
    """Build a crocheted hyperbolic form ("pseudosphere") as a mesh.

    The function follows the crochet pattern step by step:
      1. a small ring made of chain stitches,
      2. a first round of double crochets into the ring,
      3. more rounds, where every stitch gets `increase` new stitches.

    Each stitch is one mesh vertex. After every new round the stitches are
    relaxed like small springs: a stitch wants to keep its width and its
    height, and two stitches cannot be in the same place. Each round has more
    stitches than a flat circle has room for, so the surface has to ruffle.

    Params:
        rounds (int): Number of rounds worked into the ring. Default 4.
            Stitch count is multiplied by `increase` every round, so keep
            this low (5 rounds with increase 3 is already 972 stitches).
        first_round (int): Stitches in the first round. Default 12.
        increase (int): New stitches worked into each stitch. Default 3.
            1 gives a tube, 2 gives soft ruffles, 3 gives dense ruffles.
        base_chain (int): Chain stitches in the starting ring. Default 4.
            Only sets the size of the hole in the middle.
        stitch_width (float): Width of one stitch. Default 1.0.
        stitch_height (float): Height of one round. Default 2.0
            (a double crochet is about twice as tall as it is wide).
        iterations (int): Relaxation steps after each round. Default 150.
            More steps give a smoother result but take longer.
        seed (int): Seed for the small random offsets that let the surface
            ruffle. Same seed gives the same shape. Default 1.
        max_stitches (int): Safety limit on stitches in a single round.
            Rounds that would exceed it are skipped, so the form stops
            growing instead of freezing Rhino. Default 1500.

    Returns:
        Rhino.Geometry.Mesh: The crocheted surface. Each vertex is the top
        of one stitch, each ring of vertices is one round.
    """
    rng = random.Random(seed)

    points = []    # [x, y, z] of every stitch
    fixed = []     # True for stitches that must not move (the starting ring)
    springs = []   # (i, j, rest_length, stiffness)
    linked = set() # pairs joined by a spring, these are skipped in collision
    faces = []     # (a, b, c) vertex indices

    def add_spring(i, j, rest, stiffness):
        springs.append((i, j, rest, stiffness))
        linked.add((min(i, j), max(i, j)))

    # ------------------------------------------------------------------
    # 1 + 2. Starting ring (the joined chain). It stays fixed at the origin.
    # ------------------------------------------------------------------
    ring_radius = base_chain * stitch_width / (2.0 * math.pi)
    ring = []
    for i in range(first_round):
        angle = 2.0 * math.pi * i / first_round
        points.append([ring_radius * math.cos(angle),
                       ring_radius * math.sin(angle),
                       0.0])
        fixed.append(True)
        ring.append(i)

    # ------------------------------------------------------------------
    # Relaxation: springs keep stitch sizes, collisions keep stitches apart.
    # ------------------------------------------------------------------
    collision_distance = 0.9 * stitch_width

    def relax(steps):
        for _ in range(steps):
            # springs
            for i, j, rest, stiffness in springs:
                a = points[i]
                b = points[j]
                dx = b[0] - a[0]
                dy = b[1] - a[1]
                dz = b[2] - a[2]
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                if length < 1e-9:
                    continue
                move = stiffness * (length - rest) / length
                if fixed[i] and fixed[j]:
                    continue
                if fixed[i]:
                    b[0] -= dx * move
                    b[1] -= dy * move
                    b[2] -= dz * move
                elif fixed[j]:
                    a[0] += dx * move
                    a[1] += dy * move
                    a[2] += dz * move
                else:
                    move *= 0.5
                    a[0] += dx * move
                    a[1] += dy * move
                    a[2] += dz * move
                    b[0] -= dx * move
                    b[1] -= dy * move
                    b[2] -= dz * move

            # collisions: sort stitches into a grid, compare only neighbours
            cell = collision_distance
            grid = {}
            for index, p in enumerate(points):
                key = (int(math.floor(p[0] / cell)),
                       int(math.floor(p[1] / cell)),
                       int(math.floor(p[2] / cell)))
                grid.setdefault(key, []).append(index)

            for (cx, cy, cz), members in grid.items():
                for ox in (-1, 0, 1):
                    for oy in (-1, 0, 1):
                        for oz in (-1, 0, 1):
                            others = grid.get((cx + ox, cy + oy, cz + oz))
                            if not others:
                                continue
                            for i in members:
                                for j in others:
                                    if j <= i:
                                        continue
                                    if fixed[i] and fixed[j]:
                                        continue
                                    if (i, j) in linked:
                                        continue
                                    a = points[i]
                                    b = points[j]
                                    dx = b[0] - a[0]
                                    dy = b[1] - a[1]
                                    dz = b[2] - a[2]
                                    d2 = dx * dx + dy * dy + dz * dz
                                    if d2 >= cell * cell or d2 < 1e-12:
                                        continue
                                    dist = math.sqrt(d2)
                                    push = (cell - dist) / dist
                                    if fixed[i]:
                                        b[0] += dx * push
                                        b[1] += dy * push
                                        b[2] += dz * push
                                    elif fixed[j]:
                                        a[0] -= dx * push
                                        a[1] -= dy * push
                                        a[2] -= dz * push
                                    else:
                                        push *= 0.5
                                        a[0] -= dx * push
                                        a[1] -= dy * push
                                        a[2] -= dz * push
                                        b[0] += dx * push
                                        b[1] += dy * push
                                        b[2] += dz * push

    # ------------------------------------------------------------------
    # 3 + 4. Work the rounds. Round 1 puts one stitch on each ring position,
    # every later round puts `increase` stitches into each stitch.
    # ------------------------------------------------------------------
    grow_from = {}  # stitch index -> index of the stitch it was worked into

    for round_index in range(rounds):
        per_stitch = 1 if round_index == 0 else increase
        if len(ring) * per_stitch > max_stitches:
            break  # next round would be too big, stop at the last one that fits
        new_ring = []
        children_of = []

        for parent in ring:
            p = points[parent]

            # growth direction: continue the line from grandparent to parent
            if parent in grow_from:
                g = points[grow_from[parent]]
                direction = [p[0] - g[0], p[1] - g[1], p[2] - g[2]]
            else:
                direction = [p[0], p[1], 0.0]
            size = math.sqrt(sum(c * c for c in direction)) or 1.0
            direction = [c / size for c in direction]

            children = []
            for _ in range(per_stitch):
                jitter = 0.3 * stitch_width
                points.append([
                    p[0] + direction[0] * stitch_height + rng.uniform(-jitter, jitter),
                    p[1] + direction[1] * stitch_height + rng.uniform(-jitter, jitter),
                    p[2] + direction[2] * stitch_height + rng.uniform(-jitter, jitter),
                ])
                fixed.append(False)
                child = len(points) - 1
                grow_from[child] = parent
                children.append(child)
                new_ring.append(child)
                # the post of the stitch
                add_spring(parent, child, stitch_height, 1.0)
            children_of.append(children)

        count = len(new_ring)
        for k in range(count):
            # top of the round: every stitch is one stitch_width wide
            add_spring(new_ring[k], new_ring[(k + 1) % count], stitch_width, 1.0)
            # weak spring to the stitch after next, keeps the round smooth
            if count > 4:
                add_spring(new_ring[k], new_ring[(k + 2) % count],
                           2.0 * stitch_width, 0.15)

        # faces between the old round and the new round
        parents = len(ring)
        for j in range(parents):
            children = children_of[j]
            next_parent = ring[(j + 1) % parents]
            next_child = children_of[(j + 1) % parents][0]
            for k in range(len(children) - 1):
                faces.append((ring[j], children[k], children[k + 1]))
            faces.append((ring[j], children[-1], next_child))
            faces.append((ring[j], next_child, next_parent))

        ring = new_ring
        relax(iterations)

    # ------------------------------------------------------------------
    # Build the Rhino mesh
    # ------------------------------------------------------------------
    mesh = rg.Mesh()
    for p in points:
        mesh.Vertices.Add(p[0], p[1], p[2])
    for a, b, c in faces:
        mesh.Faces.AddFace(a, b, c)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


# ======================================================================
# Tangent sphere growth
# ======================================================================


def random_unit_vector():
    """Return a random direction on the unit sphere."""
    z = random.uniform(-1.0, 1.0)
    t = random.uniform(0.0, 2.0 * math.pi)
    r = math.sqrt(1.0 - z * z)
    return rg.Vector3d(r * math.cos(t), r * math.sin(t), z)


def rotate_vector(v, axis, angle_rad):
    """Rotate vector v around axis by angle (radians).

    Params:
        v (Rhino.Geometry.Vector3d): Vector to rotate. It is not changed.
        axis (Rhino.Geometry.Vector3d): Rotation axis.
        angle_rad (float): Rotation angle in radians.

    Returns:
        Rhino.Geometry.Vector3d: The rotated copy of v.
    """
    # 1.1 -- copy the input vector and the axis
    vv = rg.Vector3d(v)
    ax = rg.Vector3d(axis)

    # 1.2 -- the axis must be unit length
    ax.Unitize()

    # 1.3 -- build a Rhino rotation transform around the world origin
    xform = rg.Transform.Rotation(
        angle_rad,
        ax,
        rg.Point3d.Origin,
    )

    # 1.4 -- apply the transform to the vector (in place)
    vv.Transform(xform)

    return vv


def random_deflect(dir_vec, angle_max):
    """Deflect a direction vector by a random small rotation.

    Idea:
      - build a plane perpendicular to the direction,
      - pick a random axis in that plane,
      - rotate by a random angle up to angle_max.

    Params:
        dir_vec (Rhino.Geometry.Vector3d): Direction to deflect.
        angle_max (float): Largest deflection angle in radians.

    Returns:
        Rhino.Geometry.Vector3d: The deflected direction.
    """
    # 1.5 -- copy and unitize the incoming direction
    d = rg.Vector3d(dir_vec)
    d.Unitize()

    # choose a helper vector that is not (nearly) parallel to d
    helper = rg.Vector3d(0, 0, 1)
    if abs(rg.Vector3d.Multiply(d, helper)) > 0.95:
        helper = rg.Vector3d(0, 1, 0)

    # 1.6 -- build a perpendicular frame U, V around d
    U = rg.Vector3d.CrossProduct(d, helper)
    U.Unitize()
    V = rg.Vector3d.CrossProduct(d, U)
    V.Unitize()

    # 1.7 -- pick a random axis in the perpendicular plane
    phi = random.uniform(0.0, 2.0 * math.pi)
    axis = U * math.cos(phi) + V * math.sin(phi)

    # 1.8 -- rotate by a random angle up to angle_max
    ang = random.uniform(0.0, angle_max)
    return rotate_vector(d, axis, ang)


def cell_key(pt, cs):
    """Map a 3D point to a grid cell index (ix, iy, iz) for cell size cs."""
    return (
        int(math.floor(pt.X / cs)),
        int(math.floor(pt.Y / cs)),
        int(math.floor(pt.Z / cs)),
    )


def neighbor_keys(k):
    """Yield the 27 cell keys around and including cell k (3x3x3)."""
    x, y, z = k
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                yield (x + dx, y + dy, z + dz)


def can_place_tangent(center, r_child, grid, cs, eps=1e-6):
    """Check whether a sphere can be placed without overlapping others.

    Touching is allowed, overlapping is not. Two spheres overlap when
        distance < r_child + r_existing - eps

    Params:
        center (Rhino.Geometry.Point3d): Center of the new sphere.
        r_child (float): Radius of the new sphere.
        grid (dict): Spatial hash, cell key -> list of (center, radius).
        cs (float): Cell size of the grid.
        eps (float): Tolerance so touching spheres count as free. Default 1e-6.

    Returns:
        bool: True if the sphere fits.
    """
    k = cell_key(center, cs)

    # 2.2 -- only check spheres in nearby grid cells
    for nk in neighbor_keys(k):
        if nk not in grid:
            continue

        for (c2, r2) in grid[nk]:
            # 2.1 -- overlap rule
            if center.DistanceTo(c2) < (r_child + r2 - eps):
                return False

    return True


def add_to_grid(center, radius, grid, cs):
    """Store (center, radius) in its grid cell for fast lookup later."""
    key = cell_key(center, cs)
    # 2.3 -- store center and radius
    grid.setdefault(key, []).append((center, radius))


def grow_tangent_spheres(
    seed_pt=None,
    seed_radius=5.0,
    iterations=30,
    radius_decay=0.92,
    branch_chance=0.2,
    angle_max=0.8,
    min_radius=0.5,
    seed_dir=None,
    seed=None,
):
    """Grow a branching chain of touching spheres from a seed sphere.

    Every generation, each tip places one child sphere (sometimes two) that
    touches its parent. The child is a bit smaller and points in a slightly
    deflected direction. Children that would overlap an existing sphere are
    retried in another direction; growth stops when nothing fits anymore.

    Params:
        seed_pt (Rhino.Geometry.Point3d): Start point. Default world origin.
        seed_radius (float): Radius of the first sphere. Default 5.0.
        iterations (int): Maximum number of generations. Default 30.
        radius_decay (float): Shrink factor per generation. Default 0.92.
        branch_chance (float): Chance (0-1) that a tip gets a second child.
            Default 0.2.
        angle_max (float): Largest deflection per generation, in radians.
            Default 0.8. Below about 0.6 a second child never fits beside
            its sibling, so the growth does not branch.
        min_radius (float): Stop growing a branch when spheres get smaller
            than this. Default 0.5.
        seed_dir (Rhino.Geometry.Vector3d): Initial direction. None picks a
            random one. Default None.
        seed (int): Random seed; the same seed gives the same result.
            None gives a new result every time. Default None.

    Returns:
        tuple: (spheres, lines, tip_points)
            spheres    -- list of Rhino.Geometry.Sphere
            lines      -- list of Rhino.Geometry.Line, parent to child
            tip_points -- list of Rhino.Geometry.Point3d, the last tips
    """
    if seed_pt is None:
        seed_pt = rg.Point3d(0, 0, 0)
    if seed is not None:
        random.seed(seed)

    # STEP 3 -- initial direction: use seed_dir if given, otherwise random
    if seed_dir:
        # 3.1 -- copy and unitize seed_dir
        d0 = rg.Vector3d(seed_dir)
        d0.Unitize()
    else:
        d0 = random_unit_vector()

    spheres, lines = [], []

    # 4.1 -- cell size for the spatial hash. Two spheres can only collide
    # when their centers are closer than the sum of their radii, which is
    # at most 2 * seed_radius. With cells at least that big, checking the
    # 3x3x3 neighbouring cells is enough to find every possible collision.
    cell_size = max(2.0 * seed_radius, 2.0 * min_radius)

    grid = {}

    # 4.2 -- create the seed sphere and store it in the grid
    spheres.append(rg.Sphere(seed_pt, seed_radius))
    add_to_grid(seed_pt, seed_radius, grid, cell_size)

    # 4.3 -- tips are the active growth states: (point, direction, radius)
    tips = [(seed_pt, d0, seed_radius)]

    for i in range(iterations):

        new_tips = []

        # 4.4 -- grow from each active tip
        for (pt, d, r_parent) in tips:

            # child radius shrinks
            r_child = r_parent * radius_decay
            if r_child < min_radius:
                continue

            # 4.5 -- branching: usually 1 child, sometimes 2
            n_children = 1 + (1 if random.random() < branch_chance else 0)

            for c in range(n_children):

                # 4.6 -- try up to 20 directions to find a free placement
                for t in range(20):

                    # new direction = deflected parent direction
                    d_child = random_deflect(d, angle_max)
                    d_child.Unitize()

                    # 4.7 -- tangency rule:
                    # distance between centers = r_parent + r_child
                    step = r_parent + r_child
                    new_pt = pt + d_child * step

                    # 4.8 -- accept only if nothing overlaps
                    if can_place_tangent(new_pt, r_child, grid, cell_size, eps=1e-4):

                        spheres.append(rg.Sphere(new_pt, r_child))
                        add_to_grid(new_pt, r_child, grid, cell_size)

                        # connection line from parent to child
                        lines.append(rg.Line(pt, new_pt))

                        # the child becomes a new tip
                        new_tips.append((new_pt, d_child, r_child))
                        break  # placed, stop trying

        # 4.9 -- stop early if nothing new could be placed
        if not new_tips:
            break

        tips = new_tips

    # STEP 5 -- output only the tip points
    tip_points = [pt for (pt, d, r) in tips]

    return spheres, lines, tip_points

import System.Drawing as sd


# ======================================================================
# Constructivist floor: two tiles (A and B) and a rule that places them
# ======================================================================

# colours of the floor palette (index 0 to 7)
FLOOR_PALETTE = (
    (225, 215, 190),  # 0 paper
    (25, 22, 22),     # 1 black
    (150, 60, 40),    # 2 rust
    (215, 175, 70),   # 3 ochre
    (70, 80, 85),     # 4 slate
    (80, 55, 45),     # 5 brown
    (107, 112, 55),   # 6 olive
    (36, 72, 54),     # 7 dark green
)


def make_tile(lines=1, center=0, center_size=0.2, center_color=3,
              corner=0, corner_size=0.2, corner_color=2):
    """Describe one tile type.

    lines: 0 none, 1 bars cross, 2 curves.
    center: 0 none, 1 circle, 2 ring (in the middle of the tile).
    center_size: radius of the centre form as a fraction of the tile.
    center_color: palette index (0 to 7) of the centre form.
    corner: 0 none, 1 circle, 2 ring, 3 rectangle (a quarter of it in each tile corner).
    corner_size: radius (or half side) of the corner form as a fraction of the tile.
    corner_color: palette index (0 to 7) of the corner form.
    """
    return dict(lines=int(lines), center=int(center), center_size=float(center_size),
                center_color=int(center_color), corner=int(corner),
                corner_size=float(corner_size), corner_color=int(corner_color))


def pack_tile(lines, center, center_size, center_color, corner, corner_size, corner_color):
    """A tile as a plain list of 7 numbers, so it can travel along a Grasshopper wire."""
    return [lines, center, center_size, center_color, corner, corner_size, corner_color]


def unpack_tile(values):
    """The tile dict again, from the list made by pack_tile (or a tile dict)."""
    if isinstance(values, dict):
        return values
    return make_tile(*values)


def _line(p, q):
    return ("L", p, q)


def _arc(p, m, q):
    return ("A", p, m, q)


def _circle_loop(cx, cy, r):
    return [("C", (cx, cy), r)]


def _square_loop(cx, cy, half):
    return [_line((cx - half, cy - half), (cx + half, cy - half)),
            _line((cx + half, cy - half), (cx + half, cy + half)),
            _line((cx + half, cy + half), (cx - half, cy + half)),
            _line((cx - half, cy + half), (cx - half, cy - half))]


def _cross_loop(x0, y0, x1, y1, t):
    cx, cy, h = (x0 + x1) / 2.0, (y0 + y1) / 2.0, t / 2.0
    pts = [(x0, cy - h), (cx - h, cy - h), (cx - h, y0), (cx + h, y0), (cx + h, cy - h),
           (x1, cy - h), (x1, cy + h), (cx + h, cy + h), (cx + h, y1), (cx - h, y1),
           (cx - h, cy + h), (x0, cy + h)]
    return [_line(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts))]


def _quarter_annulus_loop(cx, cy, r_in, r_out, start_deg):
    def pt(r, deg):
        a = math.radians(deg)
        return (cx + r * math.cos(a), cy + r * math.sin(a))
    return [_line(pt(r_in, start_deg), pt(r_out, start_deg)),
            _arc(pt(r_out, start_deg), pt(r_out, start_deg + 45), pt(r_out, start_deg + 90)),
            _line(pt(r_out, start_deg + 90), pt(r_in, start_deg + 90)),
            _arc(pt(r_in, start_deg + 90), pt(r_in, start_deg + 45), pt(r_in, start_deg))]


def _form_regions(kind, cx, cy, size, negative, ring_ratio=0.38):
    """Regions of one form centred at (cx, cy).

    kind: 1 circle, 2 ring, 3 rectangle. A region is a list of loops: the
    first is the outline, the others are holes.
    Negative forms are a plate with the form cut out of it.
    """
    inner = size * (1.0 - ring_ratio)
    if not negative:
        if kind == 1:
            return [[_circle_loop(cx, cy, size)]]
        if kind == 2:
            return [[_circle_loop(cx, cy, size), _circle_loop(cx, cy, inner)]]
        return [[_square_loop(cx, cy, size)]]
    plate = _square_loop(cx, cy, size * 1.3)
    if kind == 1:
        return [[plate, _circle_loop(cx, cy, size)]]
    if kind == 2:
        return [[plate, _circle_loop(cx, cy, size)], [_circle_loop(cx, cy, inner)]]
    return [[plate, _square_loop(cx, cy, size)]]


def parse_recipe(text, default):
    """A recipe is four letters A or B, read as a 2 x 2 block: 1 2 on top, 3 4 below.

    Anything else (nothing connected, wrong length) gives the default recipe.
    """
    letters = [ch for ch in str(text or "").upper() if ch in "AB"]
    return letters if len(letters) == 4 else list(default)


def substitute_floor(recipe_a="AAAB", recipe_b="BBBA", steps=3):
    """The rule: start with one tile A and let every tile turn into four tiles.

    Every step, all tiles are replaced at once, each by the recipe of its own
    type. After `steps` steps the floor is 2**steps tiles wide and high.
    The curves of tile A flip like a chessboard, so neighbouring curves close
    into loops.

    Returns (size, cells) with cells: (i, j) -> (tile name, orientation 0 or 1),
    i going right and j going up.
    """
    recipes = {"A": parse_recipe(recipe_a, "AAAB"), "B": parse_recipe(recipe_b, "BBBA")}
    steps = max(1, min(4, int(steps)))
    cells = {(0, 0): "A"}
    size = 1
    for _ in range(steps):
        grown = {}
        for (i, j), tile in cells.items():
            top_left, top_right, bottom_left, bottom_right = recipes[tile]
            grown[(2 * i, 2 * j + 1)] = top_left
            grown[(2 * i + 1, 2 * j + 1)] = top_right
            grown[(2 * i, 2 * j)] = bottom_left
            grown[(2 * i + 1, 2 * j)] = bottom_right
        cells = grown
        size *= 2
    return size, {(i, j): (tile, (i + j) % 2) for (i, j), tile in cells.items()}


def create_constructivist_floor_shapes(recipe_a="AAAB", recipe_b="BBBA", steps=3,
                                       bar_width=0.14, negative=False,
                                       tile_a=None, tile_b=None, color_lines=1):
    """Build the floor as flat shapes (pure Python, tile size = 1).

    The two recipes and the number of steps decide which tile goes where
    (see substitute_floor). Both tiles share the bar width, so lines continue across every tile edge.
    Corner forms belong to the vertex, not to a tile: the tile whose lower left
    corner is the vertex decides the form, and all four tiles around it show it.
    That keeps the corners seamless although A and B can have different corners.

    Returns a list of shapes: dict(layer, color, regions).
    layer 0 = ground, 1 = lines, 2 = forms.
    """
    if not tile_a:  # nothing connected: use the default tiles
        tile_a = make_tile(2, 1, 0.20, 3, 1, 0.22, 2)
    if not tile_b:
        tile_b = make_tile(1, 2, 0.22, 4, 1, 0.22, 2)
    tiles = {"A": unpack_tile(tile_a), "B": unpack_tile(tile_b)}
    size, cells = substitute_floor(recipe_a, recipe_b, steps)
    width = height = size
    pal = FLOOR_PALETTE
    t = bar_width
    room = 0.5 - t / 2.0 - 0.03  # forms never touch the bar where it crosses a tile edge

    shapes = [dict(layer=0, color=pal[0],
                   regions=[[[_line((0, 0), (width, 0)), _line((width, 0), (width, height)),
                              _line((width, height), (0, height)), _line((0, height), (0, 0))]]])]

    # lines
    for (i, j), (name, orient) in cells.items():
        tile = tiles[name]
        if tile["lines"] == 1:
            shapes.append(dict(layer=1, color=pal[color_lines],
                               regions=[[_cross_loop(i, j, i + 1, j + 1, t)]]))
        elif tile["lines"] == 2:
            if orient == 0:
                centres = ((i, j, 0), (i + 1, j + 1, 180))
            else:
                centres = ((i + 1, j, 90), (i, j + 1, 270))
            shapes.append(dict(layer=1, color=pal[color_lines],
                               regions=[[_quarter_annulus_loop(cx, cy, 0.5 - t / 2.0, 0.5 + t / 2.0, a)]
                                        for cx, cy, a in centres]))

    # forms in the middle of every tile
    for (i, j), (name, orient) in cells.items():
        tile = tiles[name]
        if tile["center"] == 0:
            continue
        size = min(tile["center_size"], (0.47 / 1.3) if negative else 0.47)
        shapes.append(dict(layer=2, color=pal[tile["center_color"]],
                           regions=_form_regions(tile["center"], i + 0.5, j + 0.5, size, negative)))

    # forms on the inner grid corners, decided by the tile above and to the right
    for vj in range(1, height):
        for vi in range(1, width):
            tile = tiles[cells[(vi, vj)][0]]
            if tile["corner"] == 0:
                continue
            size = min(tile["corner_size"], (room / 1.3) if negative else room)
            shapes.append(dict(layer=2, color=pal[tile["corner_color"]],
                               regions=_form_regions(tile["corner"], vi, vj, size, negative)))
    return shapes


def _pt(p, z, module):
    return rg.Point3d(p[0] * module, p[1] * module, z)


def _loop_to_curve(loop, z, module):
    """One closed outline (list of line, arc and circle pieces) as a Rhino curve."""
    if len(loop) == 1 and loop[0][0] == "C":
        (cx, cy), r = loop[0][1], loop[0][2]
        plane = rg.Plane(rg.Point3d(cx * module, cy * module, z), rg.Vector3d.ZAxis)
        return rg.Circle(plane, r * module).ToNurbsCurve()
    poly = rg.PolyCurve()
    for seg in loop:
        if seg[0] == "L":
            poly.Append(rg.Line(_pt(seg[1], z, module), _pt(seg[2], z, module)))
        else:
            poly.Append(rg.Arc(_pt(seg[1], z, module), _pt(seg[2], z, module),
                               _pt(seg[3], z, module)))
    return poly


def floor_shapes_to_geometry(shapes, module=1.0, layer_height=0.002):
    """Turn the flat shapes into planar Breps (with holes) and one colour per Brep.

    module: size of one tile. layer_height: tiny height between the layers
    (ground, lines, forms) so that overlapping shapes do not flicker.

    Returns (breps, colors).
    """
    breps, colors = [], []
    for shape in shapes:
        z = shape["layer"] * layer_height * module
        color = sd.Color.FromArgb(*shape["color"])
        for region in shape["regions"]:
            curves = [_loop_to_curve(loop, z, module) for loop in region]
            made = rg.Brep.CreatePlanarBreps(curves, 0.001)
            for brep in made or []:
                breps.append(brep)
                colors.append(color)
    return breps, colors


def colored_mesh(breps, colors):
    """One mesh of all Breps with a vertex colour each, to show the floor in colour."""
    joined = rg.Mesh()
    params = rg.MeshingParameters.QualityRenderMesh
    for brep, color in zip(breps, colors):
        for mesh in rg.Mesh.CreateFromBrep(brep, params) or []:
            mesh.VertexColors.CreateMonotoneMesh(color)
            joined.Append(mesh)
    return joined


def create_constructivist_floor(recipe_a="AAAB", recipe_b="BBBA", steps=3,
                                tile_a=None, tile_b=None, bar_width=0.14,
                                negative=False, module=1.0, color_lines=1):
    """The whole floor: shapes -> Breps, colours and one coloured mesh.

    recipe_a, recipe_b: four letters each (A or B), what a tile turns into.
    steps: how many times all tiles are replaced (1 to 4).
    tile_a, tile_b: the two tiles, as made by pack_tile (a list of 7 numbers);
    nothing connected uses the default tiles.
    color_lines: palette index (0 to 7) of the lines.

    Returns (breps, colors, mesh).
    """
    shapes = create_constructivist_floor_shapes(
        recipe_a, recipe_b, steps, bar_width, negative, tile_a, tile_b, color_lines)
    breps, colors = floor_shapes_to_geometry(shapes, module)
    return breps, colors, colored_mesh(breps, colors)

def _derive_stitch_parents(rows):
    """Work out which stitch of the round above each stitch is worked into.

    Uses the same rule as place_fibonacci_stitches (even_stitch_pattern), so it
    only needs the stitch counts of the rounds. Returns the same `parents`
    structure as place_fibonacci_ring.
    """
    parents = [[[] for _ in rows[0]]]
    for r in range(1, len(rows)):
        pattern = even_stitch_pattern(len(rows[r - 1]), len(rows[r]))
        new_parents = []
        for i, count in enumerate(pattern):
            if count == 2:
                new_parents.extend([[i], [i]])
            elif count == 1 and i + 1 < len(pattern) and pattern[i + 1] == 0:
                new_parents.append([i, i + 1])
            elif count == 1:
                new_parents.append([i])
        parents.append(new_parents)
    return parents


def create_stitch_boxes(rows, parents=None, box_scale=0.85, darken=0.45,
                        closed=True):
    """Build every stitch as a small box and colour it by type and round.

    Each stitch gets its own local coordinate frame, built like in the
    lecture with a cross product:
        up      = from the stitch(es) it is worked into, to the stitch
        along   = direction of the round (previous to next neighbour),
                  made perpendicular to `up`
        depth   = cross product of the two
    The box is centred between the stitch and its parent, so the boxes stack
    like bricks along the fabric.

    Colours:
        increase (2 stitches into one) = terracotta
        decrease (2 stitches together)  = dark green
        normal stitch                   = sage green
    Every round is a bit darker than the one before.

    Params:
        rows: relaxed stitch points, list of rounds (Point3d).
        parents: from place_fibonacci_ring. Optional, it is worked out from
            the round lengths when left out.
        box_scale (float): Box size relative to the stitch, below 1 leaves a
            small gap between boxes. Default 0.85.
        darken (float): How much darker the last round is than the first,
            0 = no change, 0.45 = 45 percent darker. Default 0.45.
        closed (bool): True when every round is a closed ring. Default True.

    Returns:
        boxes  -- list of Rhino.Geometry.Brep, one per stitch
        colors -- list of System.Drawing.Color, same order
        mesh   -- one Rhino.Geometry.Mesh of all boxes, with vertex colours
    """
    import System.Drawing as sd

    if parents is None:
        parents = _derive_stitch_parents(rows)

    normal_rgb = (169, 183, 156)
    increase_rgb = (196, 98, 59)
    decrease_rgb = (47, 74, 51)

    # how many children has every stitch? (2 children = it was an increase)
    children = [[[] for _ in row] for row in rows]
    for r in range(1, len(rows)):
        for k, plist in enumerate(parents[r]):
            for pi in plist:
                children[r - 1][pi].append(k)

    last = max(1, len(rows) - 1)
    boxes, colors = [], []
    mesh = rg.Mesh()
    vertex_colors = []

    for r, row in enumerate(rows):
        n = len(row)
        factor = 1.0 - darken * r / last
        for k, p in enumerate(row):
            # --- what kind of stitch is it? ---
            if r > 0 and len(parents[r][k]) == 2:
                rgb = decrease_rgb
            elif r > 0 and len(children[r - 1][parents[r][k][0]]) == 2:
                rgb = increase_rgb
            else:
                rgb = normal_rgb

            # --- local frame ---
            if r > 0:
                anchors = [rows[r - 1][i] for i in parents[r][k]]
            else:
                anchors = [rows[1][i] for i in children[0][k]] if len(rows) > 1 else []
            if r > 0:
                base = rg.Point3d(sum(a.X for a in anchors) / len(anchors),
                                  sum(a.Y for a in anchors) / len(anchors),
                                  sum(a.Z for a in anchors) / len(anchors))
                up = p - base
            elif anchors:
                tip = rg.Point3d(sum(a.X for a in anchors) / len(anchors),
                                 sum(a.Y for a in anchors) / len(anchors),
                                 sum(a.Z for a in anchors) / len(anchors))
                up = tip - p
                base = p
            else:
                base = p
                up = rg.Vector3d(0, 0, -1)
            height = up.Length
            if height < 1e-9:
                up = rg.Vector3d(0, 0, 1)
                height = 1.0
            up.Unitize()

            if closed:
                prev_p, next_p = row[(k - 1) % n], row[(k + 1) % n]
            else:
                prev_p, next_p = row[max(k - 1, 0)], row[min(k + 1, n - 1)]
            along = next_p - prev_p
            along = along - up * (along * up)  # make it perpendicular to up
            if along.Length < 1e-9:
                along = rg.Vector3d.CrossProduct(up, rg.Vector3d(0, 0, 1))
            if along.Length < 1e-9:
                along = rg.Vector3d(1, 0, 0)
            along.Unitize()

            width = 0.5 * (p.DistanceTo(prev_p) + p.DistanceTo(next_p))
            if width < 1e-9:
                width = height

            # --- the box, centred between the stitch and its parent ---
            if r > 0:
                centre = rg.Point3d((p.X + base.X) / 2, (p.Y + base.Y) / 2, (p.Z + base.Z) / 2)
            else:
                centre = rg.Point3d(p.X + up.X * height / 2, p.Y + up.Y * height / 2,
                                    p.Z + up.Z * height / 2)
            plane = rg.Plane(centre, along, up)  # z axis = along x up (cross product)
            w, h = width * box_scale / 2.0, height * box_scale / 2.0
            box = rg.Box(plane, rg.Interval(-w, w), rg.Interval(-h, h), rg.Interval(-w, w))

            color = sd.Color.FromArgb(int(rgb[0] * factor), int(rgb[1] * factor),
                                      int(rgb[2] * factor))
            boxes.append(box.ToBrep())
            colors.append(color)

            box_mesh = rg.Mesh.CreateFromBox(box, 1, 1, 1)
            for _ in range(box_mesh.Vertices.Count):
                vertex_colors.append(color)
            mesh.Append(box_mesh)

    mesh.VertexColors.Clear()
    for c in vertex_colors:
        mesh.VertexColors.Add(c)
    mesh.Normals.ComputeNormals()
    return boxes, colors, mesh

def create_stitch_donuts(rows, parents=None, donut_scale=0.8, darken=0.45,
                         closed=True, tube=0.3, increase_size=0.7,
                         decrease_size=1.2):
    """Build every stitch as a small donut (torus) and colour it.

    Same frames and colours as create_stitch_boxes: every stitch gets a local
    coordinate frame (up = from its parent to the stitch, along = direction of
    the round, depth = cross product of the two). The donut lies in the
    (along, up) plane, so its hole looks out of the fabric like a yarn loop.
    It is centred between the stitch and its parent.

    Colours:
        increase (2 stitches into one) = terracotta
        decrease (2 stitches together)  = dark green
        normal stitch                   = sage green
    Every round is a bit darker than the one before.

    Params:
        rows: relaxed stitch points, list of rounds (Point3d).
        parents: from place_fibonacci_ring. Optional, it is worked out from
            the round lengths when left out.
        donut_scale (float): Outer diameter of the donut relative to the
            smaller of stitch width and height. Default 0.8.
        darken (float): How much darker the last round is than the first,
            0 = no change, 0.45 = 45 percent darker. Default 0.45.
        closed (bool): True when every round is a closed ring. Default True.
        tube (float): Thickness of the donut ring, 0.15 = thin, 0.45 = fat.
            Default 0.3.
        increase_size (float): Size of increase donuts compared to a normal
            stitch. Two stitches share the room of one, so they are smaller.
            Default 0.7, 1.0 = no change.
        decrease_size (float): Size of decrease donuts compared to a normal
            stitch. One stitch sits on two parents, so it is bigger.
            Default 1.2, 1.0 = no change.

    Returns:
        donuts -- list of Rhino.Geometry.Brep, one per stitch
        colors -- list of System.Drawing.Color, same order
        mesh   -- one Rhino.Geometry.Mesh of all donuts, with vertex colours
    """
    import System.Drawing as sd

    if parents is None:
        parents = _derive_stitch_parents(rows)

    normal_rgb = (169, 183, 156)
    increase_rgb = (196, 98, 59)
    decrease_rgb = (47, 74, 51)
    u_steps, v_steps = 16, 8  # mesh resolution around and through the donut

    children = [[[] for _ in row] for row in rows]
    for r in range(1, len(rows)):
        for k, plist in enumerate(parents[r]):
            for pi in plist:
                children[r - 1][pi].append(k)

    last = max(1, len(rows) - 1)
    donuts, colors = [], []
    mesh = rg.Mesh()

    for r, row in enumerate(rows):
        n = len(row)
        factor = 1.0 - darken * r / last
        for k, p in enumerate(row):
            # --- what kind of stitch is it? ---
            if r > 0 and len(parents[r][k]) == 2:
                rgb = decrease_rgb
                type_size = decrease_size
            elif r > 0 and len(children[r - 1][parents[r][k][0]]) == 2:
                rgb = increase_rgb
                type_size = increase_size
            else:
                rgb = normal_rgb
                type_size = 1.0

            # --- local frame (same as create_stitch_boxes) ---
            if r > 0:
                anchors = [rows[r - 1][i] for i in parents[r][k]]
            else:
                anchors = [rows[1][i] for i in children[0][k]] if len(rows) > 1 else []
            if r > 0:
                base = rg.Point3d(sum(a.X for a in anchors) / len(anchors),
                                  sum(a.Y for a in anchors) / len(anchors),
                                  sum(a.Z for a in anchors) / len(anchors))
                up = p - base
            elif anchors:
                tip = rg.Point3d(sum(a.X for a in anchors) / len(anchors),
                                 sum(a.Y for a in anchors) / len(anchors),
                                 sum(a.Z for a in anchors) / len(anchors))
                up = tip - p
                base = p
            else:
                base = p
                up = rg.Vector3d(0, 0, -1)
            height = up.Length
            if height < 1e-9:
                up = rg.Vector3d(0, 0, 1)
                height = 1.0
            up.Unitize()

            if closed:
                prev_p, next_p = row[(k - 1) % n], row[(k + 1) % n]
            else:
                prev_p, next_p = row[max(k - 1, 0)], row[min(k + 1, n - 1)]
            along = next_p - prev_p
            along = along - up * (along * up)
            if along.Length < 1e-9:
                along = rg.Vector3d.CrossProduct(up, rg.Vector3d(0, 0, 1))
            if along.Length < 1e-9:
                along = rg.Vector3d(1, 0, 0)
            along.Unitize()

            width = 0.5 * (p.DistanceTo(prev_p) + p.DistanceTo(next_p))
            if width < 1e-9:
                width = height

            if r > 0:
                centre = rg.Point3d((p.X + base.X) / 2, (p.Y + base.Y) / 2, (p.Z + base.Z) / 2)
            else:
                centre = rg.Point3d(p.X + up.X * height / 2, p.Y + up.Y * height / 2,
                                    p.Z + up.Z * height / 2)
            plane = rg.Plane(centre, along, up)

            # --- the donut: outer radius = half the scaled size, per stitch type ---
            outer = min(width, height) * donut_scale * type_size / 2.0
            minor = outer * tube
            major = outer - minor
            color = sd.Color.FromArgb(int(rgb[0] * factor), int(rgb[1] * factor),
                                      int(rgb[2] * factor))
            donuts.append(rg.Torus(plane, major, minor).ToRevSurface().ToBrep())
            colors.append(color)

            # mesh of the same donut, vertex by vertex
            x_axis, y_axis, z_axis = plane.XAxis, plane.YAxis, plane.ZAxis
            first = mesh.Vertices.Count
            for i in range(u_steps):
                u = 2.0 * math.pi * i / u_steps
                ring_dir = x_axis * math.cos(u) + y_axis * math.sin(u)
                for j in range(v_steps):
                    v = 2.0 * math.pi * j / v_steps
                    radial = major + minor * math.cos(v)
                    mesh.Vertices.Add(
                        centre.X + ring_dir.X * radial + z_axis.X * minor * math.sin(v),
                        centre.Y + ring_dir.Y * radial + z_axis.Y * minor * math.sin(v),
                        centre.Z + ring_dir.Z * radial + z_axis.Z * minor * math.sin(v))
                    mesh.VertexColors.Add(color)
            for i in range(u_steps):
                for j in range(v_steps):
                    a = first + i * v_steps + j
                    b = first + i * v_steps + (j + 1) % v_steps
                    c = first + ((i + 1) % u_steps) * v_steps + (j + 1) % v_steps
                    d = first + ((i + 1) % u_steps) * v_steps + j
                    mesh.Faces.AddFace(a, b, c, d)

    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return donuts, colors, mesh