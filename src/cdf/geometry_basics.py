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
import random
import Rhino.Geometry as rg
import System.Drawing as sd

def create_cone(base_point=None, height=10.0, radius=5.0, cap_bottom=True):
    """
    Build a cone as a Brep.

    base_point : Rhino.Geometry.Point3d -- center of the cone's base circle
    height     : float -- cone height along the base plane's normal (Z by default)
    radius     : float -- base circle radius
    cap_bottom : bool  -- whether to cap the base circle (closed vs open cone)

    Returns a Rhino.Geometry.Brep.
    """
    if base_point is None:
        base_point = rg.Point3d(0, 0, 0)

    plane = rg.Plane(base_point, rg.Vector3d.ZAxis)
    cone = rg.Cone(plane, height, radius)
    return cone.ToBrep(cap_bottom)

def create_sphere(center=None, radius=5.0):
    """
    Build a sphere as a Brep.

    center : Rhino.Geometry.Point3d -- center of the sphere
    radius : float -- sphere radius

    Returns a Rhino.Geometry.Brep.
    """
    if center is None:
        center = rg.Point3d(0, 0, 0)

    sphere = rg.Sphere(center, radius)
    return sphere.ToBrep()

def create_box(corner=None, size_x=10.0, size_y=10.0, size_z=10.0):
    """
    Build a box as a Brep.

    corner : Rhino.Geometry.Point3d -- minimum corner of the box
    size_x : float -- box size along the X axis
    size_y : float -- box size along the Y axis
    size_z : float -- box size along the Z axis

    Returns a Rhino.Geometry.Brep.
    """
    if corner is None:
        corner = rg.Point3d(0, 0, 0)

    plane = rg.Plane(corner, rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    box = rg.Box(
        plane,
        rg.Interval(0, size_x),
        rg.Interval(0, size_y),
        rg.Interval(0, size_z),
    )
    return box.ToBrep()

def create_cylinder(base_point=None, height=10.0, radius=5.0):
    """
    Build a capped cylinder as a Brep.

    base_point : Rhino.Geometry.Point3d -- center of the bottom circle
    height : float -- cylinder height along the world Z axis
    radius : float -- cylinder radius

    Returns a Rhino.Geometry.Brep.
    """
    if base_point is None:
        base_point = rg.Point3d(0, 0, 0)

    plane = rg.Plane(base_point, rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    circle = rg.Circle(plane, radius)
    cylinder = rg.Cylinder(circle, height)
    return cylinder.ToBrep(True, True)

def create_tube(base_point=None, height=10.0, outer_radius=5.0, inner_radius=3.0):
    """
    Build a hollow tube as a Brep.

    base_point : Rhino.Geometry.Point3d -- center of the bottom circle
    height : float -- tube height along the world Z axis
    outer_radius : float -- outer radius of the tube
    inner_radius : float -- inner radius of the tube

    Returns a Rhino.Geometry.Brep.
    """
    if base_point is None:
        base_point = rg.Point3d(0, 0, 0)

    plane = rg.Plane(base_point, rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    outer_circle = rg.Circle(plane, outer_radius)
    outer_cylinder = rg.Cylinder(outer_circle, height).ToBrep(True, True)

    overlap = 0.01
    inner_base = base_point - rg.Vector3d(0, 0, overlap)
    inner_plane = rg.Plane(inner_base, rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    inner_circle = rg.Circle(inner_plane, inner_radius)
    inner_cylinder = rg.Cylinder(inner_circle, height + 2 * overlap).ToBrep(True, True)

    result = rg.Brep.CreateBooleanDifference(outer_cylinder, inner_cylinder, 0.001)
    if result is None or len(result) == 0:
        return outer_cylinder
    return result[0]

def boolean_difference(brep_a, brep_b):
    """
    Perform a boolean difference operation between two Breps.

    brep_a : Rhino.Geometry.Brep -- the first Brep
    brep_b : Rhino.Geometry.Brep -- the second Brep to subtract from the first

    Returns a list of Rhino.Geometry.Brep resulting from the difference.
    """
    if brep_a is None or brep_b is None:
        raise ValueError("Both brep_a and brep_b must be provided.")

    result = rg.Brep.CreateBooleanDifference(brep_a, brep_b, 0.001)
    return result


def copy_brep_along_z(brep, distance, copy_count):
    """
    Create copies of a Brep, each offset in the +Z direction.

    brep : Rhino.Geometry.Brep -- the Brep to copy
    distance : float -- the Z spacing between consecutive copies
    copy_count : int -- the number of copies to create

    Returns a list of Rhino.Geometry.Brep copies; copy i is moved by distance * (i + 1).
    """
    if brep is None:
        raise ValueError("brep must be provided.")
    if copy_count < 0:
        raise ValueError("copy_count must not be negative.")

    copies = []
    for i in range(1, int(copy_count) + 1):
        copy = brep.DuplicateBrep()
        copy.Transform(rg.Transform.Translation(rg.Vector3d(0, 0, distance * i)))
        copies.append(copy)
    return copies


def move_brep(brep, dx=0.0, dy=0.0, dz=0.0):
    """
    Create a moved copy of a Brep.

    brep : Rhino.Geometry.Brep -- the Brep to copy and move
    dx : float -- translation distance along the X axis
    dy : float -- translation distance along the Y axis
    dz : float -- translation distance along the Z axis

    Returns a Rhino.Geometry.Brep copy translated by (dx, dy, dz).
    """
    if brep is None:
        raise ValueError("brep must be provided.")

    moved_brep = brep.DuplicateBrep()
    moved_brep.Transform(rg.Transform.Translation(rg.Vector3d(dx, dy, dz)))
    return moved_brep


def scale_brep(brep, center=None, scale_x=1.0, scale_y=1.0, scale_z=1.0):
    """
    Create a scaled copy of a Brep.

    brep : Rhino.Geometry.Brep -- the Brep to copy and scale
    center : Rhino.Geometry.Point3d -- point to scale from
    scale_x : float -- scale factor along the X axis
    scale_y : float -- scale factor along the Y axis
    scale_z : float -- scale factor along the Z axis

    Returns a Rhino.Geometry.Brep scaled from center.
    """
    if brep is None:
        raise ValueError("brep must be provided.")
    if center is None:
        center = rg.Point3d(0, 0, 0)

    plane = rg.Plane(center, rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    scaled_brep = brep.DuplicateBrep()
    scaled_brep.Transform(
        rg.Transform.Scale(plane, scale_x, scale_y, scale_z)
    )
    return scaled_brep


def rotate_brep(brep, center=None, axis=2, angle_degrees=90.0):
    """
    Create a rotated copy of a Brep.

    brep : Rhino.Geometry.Brep -- the Brep to copy and rotate
    center : Rhino.Geometry.Point3d -- point to rotate around
    axis : int -- rotation axis (0 = X, 1 = Y, 2 = Z)
    angle_degrees : float -- rotation angle in degrees

    Returns a Rhino.Geometry.Brep rotated around center.
    """
    if brep is None:
        raise ValueError("brep must be provided.")
    if axis not in (0, 1, 2):
        raise ValueError("axis must be 0 (X), 1 (Y), or 2 (Z).")
    if center is None:
        center = rg.Point3d(0, 0, 0)

    axes = (rg.Vector3d.XAxis, rg.Vector3d.YAxis, rg.Vector3d.ZAxis)
    angle_radians = math.radians(angle_degrees)
    rotated_brep = brep.DuplicateBrep()
    rotated_brep.Transform(
        rg.Transform.Rotation(angle_radians, axes[axis], center)
    )
    return rotated_brep


def random_grid_points(seed=1, nx=6, ny=6, nz=6, cell=10.0, count=20):
    """
    Create seeded random points at minimum corners of distinct grid cells.

    seed : int -- random seed
    nx : int -- number of grid cells along X
    ny : int -- number of grid cells along Y
    nz : int -- number of grid cells along Z
    cell : float -- size of one grid cell
    count : int -- number of points to return, capped at the number of cells

    Returns a list of Rhino.Geometry.Point3d.
    """
    rng = random.Random(seed)
    cells = [
        (i, j, k)
        for i in range(nx)
        for j in range(ny)
        for k in range(nz)
    ]
    chosen_cells = rng.sample(cells, min(count, len(cells)))
    return [
        rg.Point3d(i * cell, j * cell, k * cell)
        for i, j, k in chosen_cells
    ]


def boxes_at_points(points, seed=1, cell=10.0, max_span=3, slab_share=0.2):
    """
    Create randomly sized boxes at the given points.

    points : list of Rhino.Geometry.Point3d -- box minimum corners
    seed : int -- random seed
    cell : float -- size of one grid cell
    max_span : int -- maximum box size in grid cells per direction
    slab_share : float -- probability that a box is a thin slab

    Returns a list of Rhino.Geometry.Brep.
    """
    if points is None:
        raise ValueError("points must be provided.")

    rng = random.Random(seed)
    boxes = []
    for point in points:
        sizes = [
            rng.randint(1, max_span) * cell
            for _ in range(3)
        ]
        if rng.random() < slab_share:
            sizes[rng.randrange(3)] = 0.2 * cell

        boxes.append(create_box(point, sizes[0], sizes[1], sizes[2]))
    return boxes


def elements_at_points(
    points,
    seed=1,
    cell=10.0,
    sizes=None,
    bar_share=0.3,
    disc_share=0.2,
    ring_share=0.1,
    ball_share=0.1,
):
    """
    Create randomly selected flat elements at the given points.

    points : list of Rhino.Geometry.Point3d -- minimum box corners
    seed : int -- random seed
    cell : float -- size of one grid cell
    sizes : list -- size settings ordered as plate, bar, disc, ring, and ball
    bar_share : float -- probability share for bars
    disc_share : float -- probability share for discs
    ring_share : float -- probability share for rings
    ball_share : float -- probability share for balls

    Returns a tuple containing a list of Breps and their kind labels.
    """
    if points is None:
        raise ValueError("points must be provided.")
    if sizes is None:
        sizes = create_element_sizes()

    plate_span = int(sizes[0])
    bar_span = int(sizes[1])
    disc_span = int(sizes[2])
    ring_span = int(sizes[3])
    ball_size = float(sizes[4])

    rng = random.Random(seed)
    elements = []
    kinds = []
    origin = rg.Point3d(0, 0, 0)

    for point in points:
        choice = rng.random()
        if choice < bar_share:
            if rng.random() < 0.7:
                size_x = 0.3 * cell
                size_z = rng.randint(2, bar_span) * cell
            else:
                size_x = rng.randint(2, bar_span) * cell
                size_z = 0.3 * cell
            element = create_box(point, size_x, 0.3 * cell, size_z)
            kind = "bar"
        elif choice < bar_share + disc_share:
            radius = rng.randint(1, disc_span) * cell / 2.0
            height = 0.2 * cell
            element = create_cylinder(origin, height, radius)
            element = rotate_brep(element, center=origin, axis=0, angle_degrees=90.0)
            element = move_brep(
                element,
                point.X + radius,
                point.Y + height,
                point.Z + radius,
            )
            kind = "disc"
        elif choice < bar_share + disc_share + ring_share:
            outer_radius = rng.randint(1, ring_span) * cell / 2.0
            height = 0.2 * cell
            element = create_tube(
                origin, height, outer_radius, 0.6 * outer_radius
            )
            element = rotate_brep(element, center=origin, axis=0, angle_degrees=90.0)
            element = move_brep(
                element,
                point.X + outer_radius,
                point.Y + height,
                point.Z + outer_radius,
            )
            kind = "ring"
        elif choice < bar_share + disc_share + ring_share + ball_share:
            radius = rng.uniform(0.5 * ball_size * cell, ball_size * cell)
            center = rg.Point3d(
                point.X + radius,
                point.Y + radius,
                point.Z + radius,
            )
            element = create_sphere(center, radius)
            kind = "ball"
        else:
            size_x = rng.randint(1, plate_span) * cell
            size_z = rng.randint(1, plate_span) * cell
            element = create_box(point, size_x, 0.2 * cell, size_z)
            kind = "plate"

        elements.append(element)
        kinds.append(kind)

    return elements, kinds


def create_element_sizes(plate_span=3, bar_span=5, disc_span=3, ring_span=3, ball_size=0.4):
    """
    Create a list of element size settings.

    plate_span : int -- plate span
    bar_span : int -- bar span
    disc_span : int -- disc span
    ring_span : int -- ring span
    ball_size : float -- ball size

    Returns the settings in plate, bar, disc, ring, and ball order.
    """
    return [plate_span, bar_span, disc_span, ring_span, ball_size]


def create_element(kind, rng, cell=10.0, sizes=None):
    """
    Create one element with its bounding-box minimum corner at the origin.

    kind : str -- element kind: "bar", "disc", "ring", "ball", or "plate"
    rng : random.Random -- random number generator
    cell : float -- size of one grid cell
    sizes : list -- size settings ordered as plate, bar, disc, ring, and ball

    Returns a Rhino.Geometry.Brep.
    """
    if kind not in ("bar", "disc", "ring", "ball", "plate"):
        raise ValueError("kind must be 'bar', 'disc', 'ring', 'ball', or 'plate'.")
    if sizes is None:
        sizes = create_element_sizes()

    plate_span = int(sizes[0])
    bar_span = int(sizes[1])
    disc_span = int(sizes[2])
    ring_span = int(sizes[3])
    ball_size = float(sizes[4])
    origin = rg.Point3d(0, 0, 0)

    if kind == "bar":
        if rng.random() < 0.7:
            size_x = 0.3 * cell
            size_z = rng.randint(2, bar_span) * cell
        else:
            size_x = rng.randint(2, bar_span) * cell
            size_z = 0.3 * cell
        return create_box(origin, size_x, 0.3 * cell, size_z)
    if kind == "disc":
        radius = rng.randint(1, disc_span) * cell / 2.0
        height = 0.2 * cell
        element = create_cylinder(origin, height, radius)
        element = rotate_brep(element, center=origin, axis=0, angle_degrees=90.0)
        return move_brep(element, radius, height, radius)
    if kind == "ring":
        outer_radius = rng.randint(1, ring_span) * cell / 2.0
        height = 0.2 * cell
        element = create_tube(origin, height, outer_radius, 0.6 * outer_radius)
        element = rotate_brep(element, center=origin, axis=0, angle_degrees=90.0)
        return move_brep(element, outer_radius, height, outer_radius)
    if kind == "ball":
        radius = rng.uniform(0.5 * ball_size * cell, ball_size * cell)
        center = rg.Point3d(radius, radius, radius)
        return create_sphere(center, radius)

    size_x = rng.randint(1, plate_span) * cell
    size_z = rng.randint(1, plate_span) * cell
    return create_box(origin, size_x, 0.2 * cell, size_z)


def random_kinds(seed=1, count=20, bar_share=0.3, disc_share=0.2, ring_share=0.1, ball_share=0.1):
    """
    Generate seeded random element kind labels.

    seed : int -- random seed
    count : int -- number of kinds to generate
    bar_share : float -- probability share for bars
    disc_share : float -- probability share for discs
    ring_share : float -- probability share for rings
    ball_share : float -- probability share for balls

    Returns a list of kind strings.
    """
    rng = random.Random(seed)
    kinds = []
    for _ in range(count):
        choice = rng.random()
        if choice < bar_share:
            kind = "bar"
        elif choice < bar_share + disc_share:
            kind = "disc"
        elif choice < bar_share + disc_share + ring_share:
            kind = "ring"
        elif choice < bar_share + disc_share + ring_share + ball_share:
            kind = "ball"
        else:
            kind = "plate"
        kinds.append(kind)
    return kinds


def make_elements(kinds, seed=1, cell=10.0, sizes=None):
    """
    Create origin-based Breps for the requested element kinds.

    kinds : list of str -- element kinds to create
    seed : int -- random seed
    cell : float -- size of one grid cell
    sizes : list -- size settings ordered as plate, bar, disc, ring, and ball

    Returns a list of Rhino.Geometry.Brep.
    """
    if kinds is None:
        raise ValueError("kinds must be provided.")

    rng = random.Random(seed)
    return [create_element(kind, rng, cell, sizes) for kind in kinds]


def _make_shape(kind, box):
    """
    Exact analytic shape of a placed element, derived from its kind and bounding box.

    kind : str -- element kind ("bar", "plate", "disc", "ring", "ball")
    box : tuple -- (min_x, min_y, min_z, max_x, max_y, max_z)

    Returns ("box", x0, y0, z0, x1, y1, z1), ("cyl", cx, cz, radius, y0, y1)
    (a cylinder whose axis runs along Y) or ("ball", cx, cy, cz, radius).
    Rings are treated as filled discs.
    """
    x0, y0, z0, x1, y1, z1 = box
    if kind in ("disc", "ring"):
        radius = min(x1 - x0, z1 - z0) / 2.0
        return ("cyl", (x0 + x1) / 2.0, (z0 + z1) / 2.0, radius, y0, y1)
    if kind == "ball":
        radius = min(x1 - x0, y1 - y0, z1 - z0) / 2.0
        return ("ball", (x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0, radius)
    return ("box", x0, y0, z0, x1, y1, z1)


def _point_rect_distance(px, pz, x0, z0, x1, z1):
    """Distance from a point to a rectangle in the XZ plane (0 inside)."""
    return math.hypot(max(x0 - px, 0.0, px - x1), max(z0 - pz, 0.0, pz - z1))


def _point_shape_distance(px, py, pz, shape):
    """Distance from a point to a shape. For a ball the value is negative inside."""
    if shape[0] == "box":
        dx = max(shape[1] - px, 0.0, px - shape[4])
        dy = max(shape[2] - py, 0.0, py - shape[5])
        dz = max(shape[3] - pz, 0.0, pz - shape[6])
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    if shape[0] == "cyl":
        dy = max(shape[4] - py, 0.0, py - shape[5])
        dr = max(math.hypot(px - shape[1], pz - shape[2]) - shape[3], 0.0)
        return math.hypot(dy, dr)
    return math.sqrt(
        (px - shape[1]) ** 2 + (py - shape[2]) ** 2 + (pz - shape[3]) ** 2
    ) - shape[4]


def _separation(a, b):
    """
    Signed separation of two shapes: > 0 gap, 0 touching, < 0 overlapping.

    Boxes and Y-axis cylinders are a Y interval times a region in the XZ plane,
    so their distance combines the Y gap and the XZ gap exactly. Balls reduce
    to the distance from the ball center to the other shape minus the radius.
    """
    if a[0] == "ball":
        return _point_shape_distance(a[1], a[2], a[3], b) - a[4]
    if b[0] == "ball":
        return _point_shape_distance(b[1], b[2], b[3], a) - b[4]

    ay0, ay1 = (a[2], a[5]) if a[0] == "box" else (a[4], a[5])
    by0, by1 = (b[2], b[5]) if b[0] == "box" else (b[4], b[5])
    y_gap = max(ay0 - by1, by0 - ay1)

    if a[0] == "box" and b[0] == "box":
        gap_x = max(a[1] - b[4], b[1] - a[4])
        gap_z = max(a[3] - b[6], b[3] - a[6])
        if gap_x < 0 and gap_z < 0:
            xz_gap = max(gap_x, gap_z)
        else:
            xz_gap = math.hypot(max(gap_x, 0.0), max(gap_z, 0.0))
    elif a[0] == "cyl" and b[0] == "cyl":
        xz_gap = math.hypot(a[1] - b[1], a[2] - b[2]) - a[3] - b[3]
    else:
        box, cyl = (a, b) if a[0] == "box" else (b, a)
        xz_gap = _point_rect_distance(
            cyl[1], cyl[2], box[1], box[3], box[4], box[6]
        ) - cyl[3]

    if y_gap < 0 and xz_gap < 0:
        return max(y_gap, xz_gap)
    return math.hypot(max(y_gap, 0.0), max(xz_gap, 0.0))


def _slide_to_contact(kind, box, parent_shape, axis, direction, travel, tol=0.001):
    """
    Slide a candidate box along one axis toward its parent until the exact
    shapes just touch.

    kind : str -- element kind of the candidate
    box : tuple -- candidate bounding box (min_x, min_y, min_z, max_x, max_y, max_z)
    parent_shape : tuple -- exact shape of the parent from _make_shape
    axis : int -- 0 = X, 1 = Y, 2 = Z
    direction : int -- -1 or +1, the direction toward the parent
    travel : float -- maximum distance to slide

    Returns the distance to slide, or None if the shapes never touch on this line.
    """
    def separation_at(distance):
        moved = list(box)
        moved[axis] += direction * distance
        moved[axis + 3] += direction * distance
        return _separation(_make_shape(kind, tuple(moved)), parent_shape)

    if separation_at(0.0) <= tol:
        return 0.0

    # The separation along a line is convex, so a ternary search finds the closest approach.
    low, high = 0.0, travel
    for _ in range(30):
        third = (high - low) / 3.0
        if separation_at(low + third) < separation_at(high - third):
            high -= third
        else:
            low += third
    closest = (low + high) / 2.0
    if separation_at(closest) > tol:
        return None

    low, high = 0.0, closest
    for _ in range(30):
        middle = (low + high) / 2.0
        if separation_at(middle) > 0.0:
            low = middle
        else:
            high = middle
    return low


def _count_contacts(candidate, shape, boxes, shapes, tol=0.001):
    """
    Count placed elements that the candidate touches.

    candidate : tuple -- candidate bounding box
    shape : tuple -- exact shape of the candidate from _make_shape
    boxes : list of tuples -- bounding boxes of the placed elements
    shapes : list of tuples -- exact shapes of the placed elements

    Two boxes touch when their faces meet and overlap enough. If one of the two
    is round, they touch when the exact distance between the shapes is zero.
    """
    candidate_extents = tuple(
        candidate[coordinate + 3] - candidate[coordinate]
        for coordinate in range(3)
    )
    contacts = 0
    for other, other_shape in zip(boxes, shapes):
        if not all(
            candidate[coordinate] <= other[coordinate + 3] + tol
            and other[coordinate] <= candidate[coordinate + 3] + tol
            for coordinate in range(3)
        ):
            continue
        if shape[0] == "box" and other_shape[0] == "box":
            other_extents = tuple(
                other[coordinate + 3] - other[coordinate]
                for coordinate in range(3)
            )
            touches = any(
                (
                    abs(candidate[axis] - other[axis + 3]) <= tol
                    or abs(candidate[axis + 3] - other[axis]) <= tol
                )
                and all(
                    min(candidate[coordinate + 3], other[coordinate + 3])
                    - max(candidate[coordinate], other[coordinate])
                    > max(
                        tol,
                        0.1 * min(
                            candidate_extents[coordinate],
                            other_extents[coordinate],
                        ),
                    )
                    for coordinate in range(3)
                    if coordinate != axis
                )
                for axis in range(3)
            )
        else:
            touches = _separation(shape, other_shape) <= tol
        if touches:
            contacts += 1
    return contacts


def assemble_touching(
    elements,
    kinds,
    seed=1,
    front_back_share=0.4,
    frame_width=0.0,
    frame_depth=0.0,
    frame_height=0.0,
    min_contacts=2,
    max_tries=500,
):
    """
    Place elements without overlap, each touching at least min_contacts others.

    Boxes are tested by their bounding boxes. Discs, rings and balls are tested
    as exact shapes (discs and rings as cylinders along Y, balls as spheres), and
    a new element is slid along its placement axis until it really touches its
    round parent.

    elements : list of Rhino.Geometry.Brep -- origin-based Breps to place
    kinds : list of str -- kind labels corresponding to elements
    seed : int -- random seed
    front_back_share : float -- probability of placement along the Y axis
    frame_width : float -- maximum X extent centered on the first element (0 = unlimited)
    frame_depth : float -- maximum Y extent centered on the first element (0 = unlimited)
    frame_height : float -- maximum Z extent centered on the first element (0 = unlimited)
    min_contacts : int -- minimum number of already placed elements to touch
    max_tries : int -- maximum placement attempts per element

    Returns placed Breps and their corresponding kind labels.
    """
    min_contacts = max(1, int(min_contacts))
    max_tries = max(1, int(max_tries))
    if elements is None or kinds is None:
        raise ValueError("elements and kinds must be provided.")
    if len(elements) != len(kinds):
        raise ValueError("elements and kinds must have the same length.")

    rng = random.Random(seed)
    if not elements:
        return [], []

    def get_box(brep):
        bounds = brep.GetBoundingBox(True)
        return (
            bounds.Min.X, bounds.Min.Y, bounds.Min.Z,
            bounds.Max.X, bounds.Max.Y, bounds.Max.Z,
        )

    placed = [elements[0]]
    placed_kinds = [kinds[0]]
    placed_boxes = [get_box(elements[0])]
    placed_shapes = [_make_shape(kinds[0], placed_boxes[0])]
    first_box = placed_boxes[0]
    frame_center = tuple(
        (first_box[coordinate] + first_box[coordinate + 3]) / 2.0
        for coordinate in range(3)
    )
    frame_limits = (frame_width, frame_depth, frame_height)

    for element, kind in zip(elements[1:], kinds[1:]):
        own_box = get_box(element)
        size = (
            own_box[3] - own_box[0],
            own_box[4] - own_box[1],
            own_box[5] - own_box[2],
        )

        for _ in range(max_tries):
            parent_index = rng.randrange(len(placed_boxes))
            parent = placed_boxes[parent_index]
            parent_shape = placed_shapes[parent_index]
            axis = 1 if rng.random() < front_back_share else rng.choice((0, 2))
            side = rng.choice((-1, 1))
            new_min = [0.0, 0.0, 0.0]

            for coordinate in range(3):
                parent_min = parent[coordinate]
                parent_max = parent[coordinate + 3]
                if coordinate == axis:
                    new_min[coordinate] = (
                        parent_max if side > 0
                        else parent_min - size[coordinate]
                    )
                else:
                    margin = 0.2 * min(
                        size[coordinate], parent_max - parent_min
                    )
                    low = parent_min - size[coordinate] + margin
                    high = parent_max - margin
                    if low < high:
                        new_min[coordinate] = rng.uniform(low, high)
                    else:
                        new_min[coordinate] = (
                            parent_min + parent_max - size[coordinate]
                        ) / 2.0

            candidate = tuple(new_min) + tuple(
                new_min[axis_index] + size[axis_index]
                for axis_index in range(3)
            )
            shape = _make_shape(kind, candidate)

            if shape[0] != "box" or parent_shape[0] != "box":
                direction = -side
                travel = (parent[axis + 3] - parent[axis]) + size[axis]
                shift = _slide_to_contact(
                    kind, candidate, parent_shape, axis, direction, travel
                )
                if shift is None:
                    continue
                new_min[axis] += direction * shift
                candidate = tuple(new_min) + tuple(
                    new_min[axis_index] + size[axis_index]
                    for axis_index in range(3)
                )
                shape = _make_shape(kind, candidate)

            outside_frame = any(
                limit > 0
                and (
                    candidate[coordinate] < frame_center[coordinate] - limit / 2.0
                    or candidate[coordinate + 3] > frame_center[coordinate] + limit / 2.0
                )
                for coordinate, limit in enumerate(frame_limits)
            )
            if outside_frame:
                continue

            overlaps = any(
                all(
                    candidate[coordinate] < other[coordinate + 3] - 0.001
                    and other[coordinate] < candidate[coordinate + 3] - 0.001
                    for coordinate in range(3)
                )
                and _separation(shape, other_shape) < -0.001
                for other, other_shape in zip(placed_boxes, placed_shapes)
            )
            if overlaps:
                continue

            contacts = _count_contacts(
                candidate, shape, placed_boxes, placed_shapes
            )
            if contacts < min(min_contacts, len(placed_boxes)):
                continue

            moved = move_brep(element, new_min[0], new_min[1], new_min[2])
            placed.append(moved)
            placed_kinds.append(kind)
            placed_boxes.append(candidate)
            placed_shapes.append(shape)
            break

    return placed, placed_kinds


def earth_colors(kinds, seed=1, accent_share=0.3):
    """
    Generate seeded earth-tone colors for element kinds.

    kinds : list of str -- kinds to assign colors to
    seed : int -- random seed
    accent_share : float -- probability of choosing an accent color

    Returns a list of System.Drawing.Color.
    """
    rng = random.Random(seed)
    accents = ((150, 60, 40), (110, 30, 30), (215, 175, 70), (107, 112, 55))
    neutrals = (
        (225, 215, 190),
        (190, 170, 140),
        (25, 22, 22),
        (80, 55, 45),
        (70, 80, 85),
    )
    colors = []
    for _ in kinds:
        palette = accents if rng.random() < accent_share else neutrals
        colors.append(sd.Color.FromArgb(*rng.choice(palette)))
    return colors