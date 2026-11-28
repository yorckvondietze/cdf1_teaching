"""
Material processes 0 -- sand pouring as Rhino.Geometry functions for Grasshopper.

Python versions of exercises/material-processes-0/sand_pouring_geometric.ghx:

* sand_ridge_along_curve           -- a sand ridge poured along a curve
                                      (constant radius and height)
* sand_ridge_along_curve_variable  -- several ridges along the same curve, one
                                      per (radius, height) pair
* sand_cones_at_points             -- sand cones of a given volume poured at points,
                                      unioned into piles
* process_parameters               -- grain size / hole / volume / lift -> geometry
* grid_points                      -- hole grid with jitter (helper, not used
                                      by the components)
* drained_surface_mesh             -- sand left in the box (inverse cones)
* pile_surface_mesh                -- sand piles on the tray below (cones / ridges)
* drained_solid_brep               -- box minus cones / troughs (Boolean difference)
* route_connector                  -- slot path between two connector points
* sand_surface                     -- component wrapper: inputs -> box sand, piles,
                                      hole points, info  (live, use this one)
* sand_solid                       -- component wrapper: inputs -> Brep, status
* pouring_box                      -- printable pouring box from cut_lines (STL)
* cutout_generator                 -- Voronoi / Lloyd hole pattern -> points,
                                      slot, laser cut lines, voronoi, labels

Use in a GHPython 3 component, for example:

    from cdf.material_processes_0 import sand_ridge_along_curve
    a = sand_ridge_along_curve(curve, radius, height)

where `curve` is a Curve input (Item Access) and `radius` / `height` are sliders.
"""

import math
import random
import Rhino.Geometry as rg

_BLEND_CONTINUITY = [
    rg.BlendContinuity.Position,
    rg.BlendContinuity.Tangency,
    rg.BlendContinuity.Curvature,
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _offset_curve(curve, distance, tolerance):
    """Offset a curve in World XY with sharp corners and return a single curve."""
    result = curve.Offset(
        rg.Plane.WorldXY, distance, tolerance, rg.CurveOffsetCornerStyle.Sharp
    )
    if not result:
        raise ValueError("Could not offset curve by {}.".format(distance))
    if len(result) > 1:
        result = rg.Curve.JoinCurves(result, tolerance)
    return result[0]


def _blend(curve_a, curve_b, continuity):
    """Blend from the end of curve_a to the start of curve_b (bulge 1, 1)."""
    index = max(0, min(2, int(continuity)))
    return rg.Curve.CreateBlendCurve(curve_a, curve_b, _BLEND_CONTINUITY[index], 1.0, 1.0)


def _flipped(curve):
    copy = curve.DuplicateCurve()
    copy.Reverse()
    return copy


def _loft(curve_a, curve_b, loft_type=rg.LoftType.Normal):
    breps = rg.Brep.CreateFromLoft(
        [curve_a, curve_b], rg.Point3d.Unset, rg.Point3d.Unset, loft_type, False
    )
    if not breps:
        raise ValueError("Loft failed.")
    return breps[0]


def _cap(curves, tolerance):
    """Join curves into a closed loop and fill it (planar if possible, else a patch)."""
    joined = rg.Curve.JoinCurves(curves, tolerance)
    if not joined:
        raise ValueError("Could not join cap curves.")
    loop = joined[0]
    planar = rg.Brep.CreatePlanarBreps(loop, tolerance)
    if planar:
        return planar[0]
    patch = rg.Brep.CreatePatch([loop], 10, 10, tolerance)
    if patch is None:
        raise ValueError("Could not fill cap curve.")
    return patch


def _ridge_brep(curve, heights, offset_left, offset_right, count, crest_width,
                continuity, tolerance):
    """
    Shared builder for the two curve functions.

    curve        : Rhino.Geometry.Curve -- pouring path (in World XY)
    heights      : list of float -- height per pour point (last value repeats)
    offset_left  : float -- base offset distance on the positive side
    offset_right : float -- base offset distance on the negative side
    """
    if curve is None:
        raise ValueError("curve must be provided.")
    if not heights:
        raise ValueError("At least one height must be given.")

    # Divide the curve into pour points and lift each one to its cone tip.
    params = curve.DivideByCount(int(count), True)
    tips = []
    for i, t in enumerate(params):
        point = curve.PointAt(t)
        h = heights[min(i, len(heights) - 1)]
        tips.append(rg.Point3d(point.X, point.Y, point.Z + h))

    # Crest: a curve through the tips, widened slightly so it can be capped.
    crest = rg.Curve.CreateInterpolatedCurve(tips, 3, rg.CurveKnotStyle.Chord)
    top_a = _offset_curve(crest, crest_width, tolerance)
    top_b = _offset_curve(crest, -crest_width, tolerance)

    # Base: the pouring curve offset to both sides.
    base_a = _offset_curve(curve, offset_left, tolerance)
    base_b = _offset_curve(curve, -offset_right, tolerance)

    # Rounded ends: blend the two sides together at the end and the start.
    base_end = _blend(base_a, _flipped(base_b), continuity)
    base_start = _blend(_flipped(base_a), base_b, continuity)
    top_end = _blend(top_a, _flipped(top_b), continuity)
    top_start = _blend(_flipped(top_a), top_b, continuity)

    parts = [
        _loft(base_a, top_a),                                  # side A
        _loft(base_b, top_b),                                  # side B
        _loft(base_end, top_end, rg.LoftType.Straight),        # end face
        _loft(base_start, top_start, rg.LoftType.Straight),    # start face
        _cap([base_end, base_start, base_a, base_b], tolerance),  # bottom
        _cap([top_end, top_start, top_a, top_b], tolerance),      # crest
    ]
    return list(rg.Brep.JoinBreps(parts, tolerance))


# ---------------------------------------------------------------------------
# 1. ridge along a curve
# ---------------------------------------------------------------------------


def sand_ridge_along_curve(
    curve,
    radius=19.0,
    height=25.0,
    count=10,
    crest_width=0.1,
    continuity=1,
    tolerance=0.001,
):
    """
    Build a sand ridge poured along a curve.

    curve       : Rhino.Geometry.Curve -- pouring path, lying in World XY
    radius      : float -- base half-width (offset to each side of the curve)
    height      : float -- height of the ridge above the curve
    count       : int   -- number of segments the curve is divided into
    crest_width : float -- half-width of the flat crest along the top
    continuity  : int   -- end blend continuity: 0 position, 1 tangency, 2 curvature
    tolerance   : float -- model tolerance for offsets and joins

    Returns a list of Rhino.Geometry.Brep (one closed Brep when the join succeeds).
    """
    return _ridge_brep(
        curve, [height], radius, radius, count, crest_width, continuity, tolerance
    )


# ---------------------------------------------------------------------------
# 2. ridge along a curve with varying widths / heights
# ---------------------------------------------------------------------------


def sand_ridge_along_curve_variable(
    curve,
    radii=None,
    heights=None,
    count=10,
    crest_width=0.1,
    continuity=1,
    tolerance=0.001,
):
    """
    Build several sand ridges along the same curve, one per (radius, height) pair.

    Each radius is used for both the left and the right side of its ridge, so
    radii [27, 18] with heights [22, 15] give a wide, tall ridge (r 27, h 22)
    and a narrower, lower one (r 18, h 15) poured along the same path.

    curve       : Rhino.Geometry.Curve -- pouring path, lying in World XY
    radii       : list of float -- base half-width of each ridge. Default [27, 18].
    heights     : list of float -- height of each ridge. Default [22, 15].
                  If radii and heights have different lengths, the last value of
                  the shorter list is repeated (Grasshopper "longest list").
    count       : int   -- number of segments the curve is divided into
    crest_width : float -- half-width of the crest along the top
    continuity  : int   -- end blend continuity: 0 position, 1 tangency, 2 curvature
    tolerance   : float -- model tolerance for offsets and joins

    Returns a list of Rhino.Geometry.Brep, one ridge per pair.
    """
    if radii is None:
        radii = [27.0, 18.0]
    if heights is None:
        heights = [22.0, 15.0]
    if not isinstance(radii, (list, tuple)):
        radii = [radii]
    if not isinstance(heights, (list, tuple)):
        heights = [heights]
    if not radii or not heights:
        raise ValueError("radii and heights must not be empty.")

    ridges = []
    for i in range(max(len(radii), len(heights))):
        radius = float(radii[min(i, len(radii) - 1)])
        height = float(heights[min(i, len(heights) - 1)])
        ridges.extend(
            _ridge_brep(
                curve, [height], radius, radius, count, crest_width, continuity,
                tolerance,
            )
        )
    return ridges


# ---------------------------------------------------------------------------
# 3. cones at points
# ---------------------------------------------------------------------------


def sand_cones_at_points(points, volumes, slope_angle=34.0, tolerance=0.001):
    """
    Pour a sand cone of a given volume at each point and union overlapping cones.

    points      : list of Rhino.Geometry.Point3d -- cone locations (Z is ignored,
                  every cone base sits on World XY at Z = 0)
    volumes     : list of float -- positive cone volume per point (model units cubed)
    slope_angle : float -- angle of repose of the sand, in degrees above horizontal
    tolerance   : float -- tolerance for the boolean union

    Returns a tuple (cones, breps, status):
        cones  : list of Rhino.Geometry.Brep -- individual capped cones
        breps  : list of Rhino.Geometry.Brep -- unioned result (the cones if the
                 union fails)
        status : str -- description of the union result
    """
    points = list(points or [])
    volumes = list(volumes or [])
    if len(points) != len(volumes):
        raise ValueError("points and volumes must have the same number of items.")

    slope = math.tan(math.radians(slope_angle))
    down = rg.Vector3d(0.0, 0.0, -1.0)

    cones = []
    for index, (point, volume) in enumerate(zip(points, volumes)):
        volume = float(volume)
        if not math.isfinite(volume) or volume <= 0.0:
            raise ValueError(
                "Volume at index {} must be positive and finite.".format(index)
            )

        # V = pi * r^2 * h / 3 with r = h / tan(slope)  ->  solve for h
        height = (3.0 * volume * slope * slope / math.pi) ** (1.0 / 3.0)
        radius = height / slope
        apex = rg.Point3d(point.X, point.Y, height)
        cone = rg.Cone(rg.Plane(apex, down), height, radius)
        if not cone.IsValid:
            raise ValueError("Could not create a valid cone for point {}.".format(index))
        cones.append(cone.ToBrep(True))

    union = rg.Brep.CreateBooleanUnion(cones, tolerance) if cones else None
    breps = [b for b in union if b is not None] if union else []

    if breps:
        status = "Solid union succeeded: {} Brep(s) from {} cone(s).".format(
            len(breps), len(cones)
        )
    elif cones:
        breps = cones
        status = "Warning: solid union failed; returning the {} cone(s).".format(
            len(cones)
        )
    else:
        status = "No cones to union."

    return cones, breps, status


# ---------------------------------------------------------------------------
# 4. drained funnel field (assignment 3): box with holes, sand drains out
# ---------------------------------------------------------------------------
#
# A box with a perforated bottom is filled with sand and held lift_height above
# a tray. Sand drains through each hole:
#   * above: an inverted cone (crater) at the angle of repose. All craters share
#     the same angle, so their ridges are the Voronoi edges of the holes.
#   * below: a pile (cone) holding exactly the volume its crater lost.
# The pile grows until it touches the box bottom (choke), so a crater can never
# get deeper than lift_height (same angle above and below).
#
# Coordinates: tray at Z = 0, box bottom at Z = lift_height. The geometry
# functions work in box coordinates (0,0)..(box_x, box_y); the component wrappers
# center the box over the input points and move the result there. Units: mm.

# grain size (mm) -> angle of repose (deg), after the slide "Angle of repose in
# dry sand": fine sand 35, coarse sand 40, angular pebbles 45.
_GRAIN_ANGLE_TABLE = [
    (0.25, 35.0),   # fine sand (0.1-0.25 mm) and finer
    (1.00, 40.0),   # coarse sand (0.5-1 mm)
    (4.00, 45.0),   # angular pebbles / grit (few mm) and coarser
]

# Pile tip vs. pouring (drop) height -- after the sketch:
#   low drop  -> sharp tip
#   mid drop  -> rounded tip
#   high drop -> dent (crater) in the tip
# Values in mm, rough guesses: calibrate them with your physical tests.
DROP_SHARP = 15.0     # below this drop the tip stays perfectly sharp
DROP_ROUND = 60.0     # tip rounding reaches its maximum at this drop
ROUND_MAX = 1.5       # max tip rounding radius, in stream radii
DROP_DENT = 50.0      # above this drop the falling stream digs a dent
DENT_RATE = 0.06      # dent depth per mm of drop above DROP_DENT
STREAM_SPREAD = 0.04  # stream radius grows by this per mm of drop

# Time / flow (after the add-on): Beverloo law, empirical constants.
GRAVITY = 9810.0      # mm/s^2
BEVERLOO_C = 0.58
BEVERLOO_K = 1.5
SLOT_PITCH = 1.125    # slot flow = 1 + length / (SLOT_PITCH * hole_diameter)
                      # equivalent holes (add-on: 9 mm pitch for 8 mm holes)


def angle_from_grain_size(grain_size):
    """Linear interpolation in the table above; clamped at the ends."""
    table = _GRAIN_ANGLE_TABLE
    if grain_size <= table[0][0]:
        return table[0][1]
    for (d0, a0), (d1, a1) in zip(table, table[1:]):
        if grain_size <= d1:
            t = (grain_size - d0) / (d1 - d0)
            return a0 + t * (a1 - a0)
    return table[-1][1]


def process_parameters(box_x, box_y, sand_volume, grain_size, hole_diameter,
                       lift_height, angle_override=None):
    """
    Translate the physical inputs into geometry inputs + warnings.

    sand_volume   : mm^3 poured into the box  -> fill depth
    grain_size    : mm (median)               -> angle of repose
    hole_diameter : mm                        -> crater bottom, stream width, jamming
    lift_height   : mm, box bottom above tray -> crater depth limit, pile tip shape
    """
    warnings = []
    depth = sand_volume / float(box_x * box_y)
    angle = angle_override if angle_override else angle_from_grain_size(grain_size)

    # Arching: holes smaller than ~5 grain diameters jam (Beverloo / silo literature).
    jammed = hole_diameter < 5.0 * grain_size
    if jammed:
        warnings.append(
            "Hole {:.1f} mm < 5 x grain {:.2f} mm: holes jam, no craters.".format(
                hole_diameter, grain_size))

    # crater depth is solved later (solve_drain): full drain unless the piles
    # below reach the box bottom and choke the holes
    crater_depth = depth

    # Beverloo flow rate through one hole (bulk volume, mm^3/s):
    # Q = C * sqrt(g) * (D - k*d)^2.5, C ~ 0.58, k ~ 1.5 (empirical)
    flow = 0.0 if jammed else BEVERLOO_C * math.sqrt(GRAVITY) * max(
        0.0, hole_diameter - BEVERLOO_K * grain_size) ** 2.5

    return {
        "depth": depth,
        "flow_hole": flow,
        "hole_diameter": hole_diameter,
        "crater_depth": crater_depth,
        "angle": angle,
        "slope": math.tan(math.radians(angle)),
        "hole_radius": 0.5 * hole_diameter,
        "lift": max(lift_height, 0.0),
        "jammed": jammed,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# hole positions
# ---------------------------------------------------------------------------


def grid_points(box_x, box_y, count_x, count_y, jitter=0.0, seed=0,
                stagger=False, margin=10.0):
    """
    Regular grid of hole positions with optional random jitter.
    jitter is a fraction of the grid spacing (0 .. 0.5).
    """
    rnd = random.Random(seed)
    sx = (box_x - 2 * margin) / max(count_x, 1)
    sy = (box_y - 2 * margin) / max(count_y, 1)
    pts = []
    for j in range(count_y):
        for i in range(count_x):
            x = margin + (i + 0.5) * sx
            y = margin + (j + 0.5) * sy
            if stagger and j % 2:
                x += 0.5 * sx
                if x > box_x - margin:
                    continue
            x += rnd.uniform(-jitter, jitter) * sx
            y += rnd.uniform(-jitter, jitter) * sy
            pts.append(rg.Point3d(x, y, 0.0))
    return pts


def clamp_points(points, box_x, box_y, margin=0.0):
    """Project points to Z = 0 and keep them inside the box."""
    out = []
    for p in points:
        x = min(max(p.X, margin), box_x - margin)
        y = min(max(p.Y, margin), box_y - margin)
        out.append(rg.Point3d(x, y, 0.0))
    return out


# ---------------------------------------------------------------------------
# mesh helpers
# ---------------------------------------------------------------------------


def _grid_mesh(xs, ys, zs, skip_flat_below=None):
    """Quad mesh from a height grid. Optionally drop faces lying flat at Z=0."""
    nx = len(xs)
    mesh = rg.Mesh()
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            mesh.Vertices.Add(x, y, zs[j * nx + i])
    for j in range(len(ys) - 1):
        for i in range(nx - 1):
            a = j * nx + i
            ids = (a, a + 1, a + nx + 1, a + nx)
            if skip_flat_below is not None and all(
                    zs[k] <= skip_flat_below for k in ids):
                continue
            mesh.Faces.AddFace(*ids)
    return mesh


def _close_heightfield(mesh, nx, ny, base_z):
    """Add a bottom vertex under every boundary vertex, stitch walls, cap bottom."""
    loop = [i for i in range(nx)]
    loop += [j * nx + (nx - 1) for j in range(1, ny)]
    loop += [(ny - 1) * nx + i for i in range(nx - 2, -1, -1)]
    loop += [j * nx for j in range(ny - 2, 0, -1)]

    base = []
    for idx in loop:
        v = mesh.Vertices[idx]
        base.append(mesh.Vertices.Add(v.X, v.Y, base_z))
    n = len(loop)
    for k in range(n):
        a, b = loop[k], loop[(k + 1) % n]
        mesh.Faces.AddFace(a, base[k], base[(k + 1) % n], b)
    bb = mesh.GetBoundingBox(True)
    c = mesh.Vertices.Add(bb.Center.X, bb.Center.Y, base_z)
    for k in range(n):
        mesh.Faces.AddFace(c, base[(k + 1) % n], base[k])


def _axis(length, resolution):
    n = max(2, int(round(length / resolution)) + 1)
    step = length / (n - 1)
    return [i * step for i in range(n)], step


# geometry 1a: drain sources (holes and slot curves)
# ---------------------------------------------------------------------------
#
# A drain source is either a single hole (point) or a slot along a curve.
# Every geometry function only needs the horizontal distance to the nearest
# source, so holes and curves behave the same way:
#   hole  -> crater is an inverted cone,  pile is a cone
#   curve -> crater is a V-trough,        pile is a ridge with conical ends


def make_sources(holes=None, curve=None):
    """List of drain sources: {'kind': 'point', 'geo': Point3d} / 'curve'."""
    sources = [{"kind": "point", "geo": p} for p in (holes or [])]
    if curve is not None:
        sources.append({"kind": "curve", "geo": curve})
    return sources


def _distance(source, x, y):
    """Horizontal distance from (x, y) to a source (sources lie at Z = 0)."""
    geo = source["geo"]
    if source["kind"] == "point":
        return math.hypot(x - geo.X, y - geo.Y)
    pt = rg.Point3d(x, y, 0.0)
    ok, t = geo.ClosestPoint(pt)
    return pt.DistanceTo(geo.PointAt(t)) if ok else float("inf")


def _source_bbox(source):
    """(xmin, xmax, ymin, ymax) of a source."""
    geo = source["geo"]
    if source["kind"] == "point":
        return geo.X, geo.X, geo.Y, geo.Y
    bb = geo.GetBoundingBox(True)
    return bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y


def interpolated_curve(points):
    """Interpolated curve through the points at Z = 0 (degree 3, or less)."""
    pts = [rg.Point3d(p.X, p.Y, 0.0) for p in points]
    if len(pts) < 2:
        return None
    return rg.Curve.CreateInterpolatedCurve(pts, min(3, len(pts) - 1),
                                            rg.CurveKnotStyle.Chord)


# ---------------------------------------------------------------------------
# geometry 1b: grids, crater field and pile field
# ---------------------------------------------------------------------------
#
# Volume is conserved: the piles on the tray hold exactly the volume that left
# the box. The pile heights are solved numerically on the actual pile surface
# (incl. overlaps, rounded tips and dents), so changing lift_height only changes
# the shape, not the amount of sand. If the piles would have to be taller than
# lift_height, they choke the holes: then less sand drains and the craters stay
# shallower (solved as well).


def _axis_with(lo, hi, resolution, extra=()):
    """Regular axis from lo to hi, plus extra coordinates (hole centres) so that
    crater bottoms and pile tips are sampled exactly."""
    n = max(2, int(round((hi - lo) / resolution)) + 1)
    vals = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    vals += [e for e in extra if lo < e < hi]
    return sorted(set(round(v, 6) for v in vals))


def _weights(axis):
    """Trapezoid integration weights of an axis."""
    n = len(axis)
    return [(axis[min(i + 1, n - 1)] - axis[max(i - 1, 0)]) / 2.0 for i in range(n)]


def _point_coords(sources):
    pts = [s["geo"] for s in sources if s["kind"] == "point"]
    return [p.X for p in pts], [p.Y for p in pts]


class _CraterField(object):
    """Distance field of the box grid: per grid point the nearest source
    (distance minus hole radius). Crater shape for any depth D is then cheap."""

    def __init__(self, sources, box_x, box_y, hole_radius, resolution):
        ex, ey = _point_coords(sources)
        self.xs = _axis_with(0.0, box_x, resolution, ex)
        self.ys = _axis_with(0.0, box_y, resolution, ey)
        wx, wy = _weights(self.xs), _weights(self.ys)
        self.n_sources = len(sources)
        self.dist, self.owner, self.w = [], [], []
        for j, y in enumerate(self.ys):
            for i, x in enumerate(self.xs):
                best, owner = float("inf"), -1
                for k, s in enumerate(sources):
                    d = max(_distance(s, x, y) - hole_radius, 0.0)
                    if d < best:
                        best, owner = d, k
                self.dist.append(best)
                self.owner.append(owner)
                self.w.append(wx[i] * wy[j])

        self.cells = [[] for _ in sources]          # per source: (dist, weight)
        for d, k, w in zip(self.dist, self.owner, self.w):
            if k >= 0:
                self.cells[k].append((d, w))

    def removed(self, depth_d, slope):
        return [max(0.0, depth_d - slope * d) for d in self.dist]

    def removed_per_source(self, depths, slope):
        """Crater with an individual depth per source (time stepping)."""
        return [max(0.0, depths[k] - slope * d) if k >= 0 else 0.0
                for d, k in zip(self.dist, self.owner)]

    def source_volume(self, k, depth_d, slope):
        return sum(max(0.0, depth_d - slope * d) * w for d, w in self.cells[k])

    def depth_for_volume(self, k, volume, max_depth, slope):
        if volume <= 0.0:
            return 0.0
        return _bisect(lambda dd: self.source_volume(k, dd, slope),
                       0.0, max_depth, volume, 30)

    def volumes(self, depth_d, slope):
        vols = [0.0] * self.n_sources
        for r, k, w in zip(self.removed(depth_d, slope), self.owner, self.w):
            if k >= 0 and r > 0.0:
                vols[k] += r * w
        return vols


def _pile_tip(drop, hole_radius):
    """
    Tip rounding radius, dent depth and dent radius for a given drop height
    (gap between pile tip and box bottom at the end).
    Rounding grows quadratically -> low drops stay really sharp.
    """
    stream = hole_radius + STREAM_SPREAD * drop
    t = (drop - DROP_SHARP) / (DROP_ROUND - DROP_SHARP)
    t = min(1.0, max(0.0, t))
    round_r = ROUND_MAX * stream * t * t
    dent = DENT_RATE * max(0.0, drop - DROP_DENT)
    return round_r, dent, 1.5 * stream


def _pile_z(rho, height, slope, round_r, dent, dent_r):
    """Cone/ridge profile with a rounded (parabolic, tangent) tip and optional dent."""
    if rho < round_r:
        z = height - slope * (rho * rho / (2.0 * round_r) + 0.5 * round_r)
    else:
        z = height - slope * rho
    if dent > 0.0 and rho < dent_r:
        z -= dent * (1.0 - (rho / dent_r) ** 2) ** 2
    return max(z, 0.0)


def _pile_height(source, volume, slope):
    """
    Ideal height of a lone pile holding `volume` (start value for the solver).
    point: cone   V = pi h^3 / (3 s^2)
    curve: ridge  V = L h^2 / s  +  pi h^3 / (3 s^2)   (two half-cone ends)
    """
    if volume <= 0.0:
        return 0.0
    if source["kind"] == "point":
        return (3.0 * volume * slope * slope / math.pi) ** (1.0 / 3.0)
    length = source["geo"].GetLength()
    vol = lambda h: length * h * h / slope + math.pi * h ** 3 / (3.0 * slope * slope)
    lo, hi = 0.0, 1.0
    while vol(hi) < volume:
        hi *= 2.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if vol(mid) < volume else (lo, mid)
    return 0.5 * (lo + hi)


class _PileField(object):
    """Pile grid on the tray with precomputed distances to every source that can
    reach a grid point (max reach = lift / slope)."""

    def __init__(self, sources, params, resolution):
        slope, lift = params["slope"], params["lift"]
        reach = lift / slope + resolution
        boxes = [_source_bbox(s) for s in sources]
        ex, ey = _point_coords(sources)
        self.xs = _axis_with(min(b[0] for b in boxes) - reach,
                             max(b[1] for b in boxes) + reach, resolution, ex)
        self.ys = _axis_with(min(b[2] for b in boxes) - reach,
                             max(b[3] for b in boxes) + reach, resolution, ey)
        wx, wy = _weights(self.xs), _weights(self.ys)
        self.entries, self.w = [], []
        for j, y in enumerate(self.ys):
            for i, x in enumerate(self.xs):
                near = []
                for k, (s, b) in enumerate(zip(sources, boxes)):
                    if b[0] - reach <= x <= b[1] + reach and \
                            b[2] - reach <= y <= b[3] + reach:
                        rho = _distance(s, x, y)
                        if rho < reach:
                            near.append((k, rho))
                self.entries.append(near)
                self.w.append(wx[i] * wy[j])

    def heights_field(self, piles, slope, lift):
        zs = []
        for near in self.entries:
            z = 0.0
            for k, rho in near:
                pl = piles[k]
                if pl is None or rho * slope >= pl["height"]:
                    continue
                z = max(z, _pile_z(rho, pl["height"], slope,
                                   pl["round_r"], pl["dent"], pl["dent_r"]))
            zs.append(min(z, lift))
        return zs

    def volume(self, piles, slope, lift):
        return sum(z * w for z, w in zip(self.heights_field(piles, slope, lift),
                                         self.w))


def _make_piles(h0, delta, volumes, params):
    """Pile dicts for start heights h0 shifted by delta (capped at lift)."""
    lift, rh = params["lift"], params["hole_radius"]
    piles = []
    for h, v in zip(h0, volumes):
        if v <= 0.0:
            piles.append(None)
            continue
        height = min(max(h + delta, 0.0), lift)
        drop = lift - height
        round_r, dent, dent_r = _pile_tip(drop, rh)
        piles.append({"volume": v, "height": height, "drop": drop,
                      "round_r": round_r, "dent": dent, "dent_r": dent_r})
    return piles


def _bisect(f, lo, hi, target, steps=30):
    """Find x in [lo, hi] with f(x) = target for increasing f."""
    for _ in range(steps):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
    return 0.5 * (lo + hi)


def source_flow(source, params):
    """Flow rate of a source (mm^3/s): one hole, or a slot as equivalent holes."""
    q = params["flow_hole"]
    if source["kind"] == "point":
        return q
    units = 1.0 + source["geo"].GetLength() / (SLOT_PITCH * params["hole_diameter"])
    return q * units


def solve_drain(sources, box_x, box_y, params, resolution=2.0, time=None):
    """
    Couple box and tray with volume conservation.

    1. Full drain: crater depth = fill depth, drained volume per source.
    2. Pile heights: ideal heights + a common shift, solved so that the real pile
       surface (overlaps, tips, cap at lift) holds exactly the drained volume.
    3. If even piles touching the box cannot hold it, the holes choke: the
       crater depth is reduced until drained volume = what fits below the box.
    4. time (% of completion, 0..100): every source drains with its Beverloo
       flow rate until its final volume is out. Craters get an individual depth,
       piles are re-solved. None / 100 = final state.

    Sets params crater_depth / crater_depths / t_end / time.
    Returns (crater_field, pile_field, piles).
    """
    slope, lift, depth = params["slope"], params["lift"], params["depth"]
    crater = _CraterField(sources, box_x, box_y, params["hole_radius"], resolution)
    params["crater_depths"] = [0.0] * len(sources)
    params["t_end"], params["time"] = 0.0, None
    if params["jammed"] or not sources or lift <= 0.0:
        params["crater_depth"] = 0.0
        return crater, None, []

    D = depth
    volumes = crater.volumes(D, slope)
    total = sum(volumes)
    if total <= 0.0:
        params["crater_depth"] = 0.0
        return crater, None, []

    # coarse pile grid for the solve, fine grid for the final mesh
    coarse = _PileField(sources, params, max(2.0 * resolution, 6.0))

    def solve_piles(vols):
        h0 = [_pile_height(s, v, slope) for s, v in zip(sources, vols)]
        vol_of = lambda dl: coarse.volume(_make_piles(h0, dl, vols, params),
                                          slope, lift)
        lo, hi = -max(h0), lift
        return h0, lo, hi, vol_of

    h0, lo, hi, vol_of = solve_piles(volumes)
    capacity = vol_of(hi)

    if total > capacity:
        # choke: drain only what fits below the box
        D = _bisect(lambda d: sum(crater.volumes(d, slope)), 0.0, depth, capacity)
        volumes = crater.volumes(D, slope)
        params["warnings"].append(
            "Piles touch the box and choke the holes: craters stop at "
            "{:.0f} of {:.0f} mm.".format(D, depth))
        h0, lo, hi, vol_of = solve_piles(volumes)
        delta = hi
    else:
        delta = _bisect(vol_of, lo, hi, sum(volumes))
    params["crater_depth"] = D
    params["crater_depths"] = [D] * len(sources)
    params["drained_total"] = sum(volumes)

    # --- time: partial drain ---------------------------------------------------
    rates = [source_flow(s, params) for s in sources]
    params["t_end"] = max([v / q for v, q in zip(volumes, rates) if q > 0] or [0.0])
    # time = percent of completion (0 .. 100) -> seconds
    if time is not None and float(time) < 100.0:
        t = params["t_end"] * max(float(time), 0.0) / 100.0
        params["time"] = t
        partial = [min(q * t, v) for q, v in zip(rates, volumes)]
        params["crater_depths"] = [crater.depth_for_volume(k, v, D, slope)
                                   for k, v in enumerate(partial)]
        volumes = partial
        if sum(volumes) <= 0.0:
            return crater, None, []
        h0, lo, hi, vol_of = solve_piles(volumes)
        delta = _bisect(vol_of, lo, hi, sum(volumes))

    piles = _make_piles(h0, delta, volumes, params)
    return crater, _PileField(sources, params, resolution), piles


def drained_surface_mesh(crater, params, closed=True):
    """Sand left in the box (sits on the box bottom, Z = lift_height)."""
    base = params["lift"]
    depths = params.get("crater_depths")
    if depths and len(depths) == crater.n_sources:
        removed = crater.removed_per_source(depths, params["slope"])
    else:
        removed = crater.removed(params["crater_depth"], params["slope"])
    zs = [base + params["depth"] - r for r in removed]
    mesh = _grid_mesh(crater.xs, crater.ys, zs)
    if closed:
        _close_heightfield(mesh, len(crater.xs), len(crater.ys), base)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def pile_surface_mesh(pile_field, piles, params):
    """Piles on the tray (Z = 0). Returns a mesh or None."""
    if pile_field is None or not any(piles):
        return None
    zs = pile_field.heights_field(piles, params["slope"], params["lift"])
    mesh = _grid_mesh(pile_field.xs, pile_field.ys, zs, skip_flat_below=1e-6)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


# ---------------------------------------------------------------------------
# geometry 2: Brep Boolean difference (exact, slower) -- sand in the box
# ---------------------------------------------------------------------------


def _cone_cutter(x, y, apex_z, height, slope):
    cone = rg.Cone(rg.Plane(rg.Point3d(x, y, apex_z), rg.Vector3d.ZAxis),
                   height, height / slope)
    return cone.ToBrep(True)


def _trough_cutter(curve, z_bot, z_top, hole_radius, slope, tolerance):
    """V-trough along a curve: swept trapezoid profile, capped."""
    t0 = curve.TangentAtStart
    normal = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, t0)
    normal.Unitize()
    start = curve.PointAtStart
    w_top = hole_radius + (z_top - z_bot) / slope

    def p(w, z):
        return rg.Point3d(start.X + normal.X * w, start.Y + normal.Y * w, z)

    # reach a bit below the crater bottom (narrower, same slope), so the trough
    # bottom is not coplanar with the box bottom (Boolean robustness)
    z_low = z_bot - 0.5 * hole_radius * slope
    w_low = 0.5 * hole_radius
    profile = rg.PolylineCurve([p(-w_top, z_top), p(-w_low, z_low),
                                p(w_low, z_low), p(w_top, z_top),
                                p(-w_top, z_top)])
    rail = curve.DuplicateCurve()
    rail.Translate(rg.Vector3d(0, 0, z_bot))
    sweeps = rg.Brep.CreateFromSweep(rail, profile, False, tolerance)
    if not sweeps:
        return None
    trough = sweeps[0].CapPlanarHoles(tolerance) or sweeps[0]
    return trough


def drained_solid_brep(sources, box_x, box_y, params, tolerance=0.01):
    """
    Box of sand minus one inverted cone per hole / one V-trough (with conical
    ends) per curve, sitting on the box bottom (Z = lift_height).
    Returns (breps, status).
    """
    depth, D = params["depth"], params["crater_depth"]
    slope, rh, base = params["slope"], params["hole_radius"], params["lift"]
    box = rg.Box(
        rg.Plane.WorldXY,
        rg.Interval(0, box_x), rg.Interval(0, box_y),
        rg.Interval(base, base + depth),
    ).ToBrep()
    if params["jammed"] or not sources or D <= 0.0:
        return [box], "No craters (jammed, no sources or no lift)."

    margin = 1.0
    z_bot = base + depth - D
    z_top = base + depth + margin
    apex_z = z_bot - rh * slope          # radius = r_hole at crater bottom
    height = z_top - apex_z
    # Every cutter gets a slightly different top height: identical, overlapping,
    # coplanar cap faces above the sand are what makes Rhino's Boolean fail.
    cutters = []
    k = [0]

    def extra():
        k[0] += 1
        return 2.0 + 0.37 * k[0]

    for s in sources:
        geo = s["geo"]
        if s["kind"] == "point":
            cutters.append(_cone_cutter(geo.X, geo.Y, apex_z, height + extra(), slope))
        else:
            trough = _trough_cutter(geo, z_bot, z_top + extra(), rh, slope, tolerance)
            if trough is not None:
                cutters.append(trough)
            for end in (geo.PointAtStart, geo.PointAtEnd):
                cutters.append(_cone_cutter(end.X, end.Y, apex_z, height + extra(),
                                            slope))

    # clean cutters: closed and outward oriented (an inward cutter turns the
    # difference into garbage)
    clean = []
    for c in cutters:
        if c is None or not c.IsSolid:
            continue
        if c.SolidOrientation == rg.BrepSolidOrientation.Inward:
            c.Flip()
        clean.append(c)
    cutters = clean

    # expected volume of the sand left in the box (from the height-field model)
    expected = box_x * box_y * depth - params.get("drained_total", 0.0)

    def plausible(b):
        if b is None or not b.IsSolid:
            return False
        props = rg.VolumeMassProperties.Compute(b)
        if props is None:
            return False
        return abs(props.Volume - expected) <= 0.04 * expected

    # all at once first, then one cutter at a time (more robust)
    result = rg.Brep.CreateBooleanDifference([box], cutters, tolerance)
    if result and len(result) == 1 and plausible(result[0]):
        return list(result), "Boolean difference OK: {} cutter(s).".format(len(cutters))
    solid, failed = box, 0
    for c in cutters:
        diff = rg.Brep.CreateBooleanDifference(solid, c, tolerance)
        if diff:
            solid = max(diff, key=lambda b: rg.VolumeMassProperties.Compute(b).Volume
                        if b.IsSolid else 0.0)
        else:
            failed += 1
    if failed == 0 and plausible(solid):
        return [solid], "Boolean difference OK (step by step): {} cutter(s).".format(
            len(cutters))
    return None, "Boolean failed for {} of {} cutter(s).".format(failed, len(cutters))


# ---------------------------------------------------------------------------
# 5. component wrappers (assignment 3) -- one call per GH component
# ---------------------------------------------------------------------------


def _parse_indices(exclude, count):
    """Panel / list input -> set of valid indices (negative = from the end)."""
    out = set()
    if exclude is None:
        exclude = []
    elif isinstance(exclude, (int, float, str)):
        exclude = [exclude]          # input set to Item Access
    for e in exclude:
        try:
            i = int(float(str(e).strip()))
        except ValueError:
            continue
        if -count <= i < count:
            out.add(i % count)
    return out


def _as_curve(slot):
    """Slot input -> one curve or None (accepts a list / item)."""
    if slot is None:
        return None
    if isinstance(slot, (list, tuple)):
        slot = next((s for s in slot if s is not None), None)
    return slot if slot is not None and hasattr(slot, "ClosestPoint") else None


def _sources_from_inputs(points, box_x, box_y, slot=None, relative=True):
    """
    Place the points (and the slot curve) in the box, then build the sources.

    relative on  : points are 0..1 box coordinates, the slot curve is in box mm
                   coordinates (as the cutout generator delivers them),
                   box sits at the world origin
    relative off : points / slot are world coordinates, box centered on points

    Returns (sources, holes, curve, origin, warnings) -- in box coordinates.
    Holes lying on the slot (its connector points) are not counted twice.
    """
    warnings = []
    if isinstance(points, rg.Point3d):
        points = [points]            # input set to Item Access
    pts = [p for p in (points or []) if p is not None]
    curve = _as_curve(slot)
    if curve is not None:
        curve = curve.DuplicateCurve()
    if not pts and curve is None:
        return [], [], None, rg.Vector3d(0, 0, 0), warnings
    if relative:
        origin = rg.Vector3d(0, 0, 0)
        if any(not (0.0 <= p.X <= 1.0 and 0.0 <= p.Y <= 1.0) for p in pts):
            warnings.append("Relative points must be 0..1: outer holes pushed "
                            "to the wall.")
        local = clamp_points(
            [rg.Point3d(p.X * box_x, p.Y * box_y, 0.0) for p in pts],
            box_x, box_y)
    else:
        ref = pts or [curve.PointAtStart, curve.PointAtEnd]
        xs = [p.X for p in ref]
        ys = [p.Y for p in ref]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        origin = rg.Vector3d(cx - 0.5 * box_x, cy - 0.5 * box_y, 0.0)
        if (max(xs) - min(xs) > box_x) or (max(ys) - min(ys) > box_y):
            warnings.append("Points spread wider than the box: outer holes "
                            "pushed to the wall.")
        local = clamp_points(
            [rg.Point3d(p.X - origin.X, p.Y - origin.Y, 0.0) for p in pts],
            box_x, box_y)
        if curve is not None:
            curve.Translate(-origin)

    if curve is not None:
        on_slot = lambda p: _distance({"kind": "curve", "geo": curve}, p.X, p.Y) < 1.0
        local = [p for p in local if not on_slot(p)]
    return make_sources(local, curve), local, curve, origin, warnings


def _to_world(geometry, origin):
    """Move a mesh / Brep / curve / point (or a list) from box to world coords."""
    if geometry is None:
        return None
    if isinstance(geometry, list):
        return [_to_world(g, origin) for g in geometry]
    if isinstance(geometry, rg.Point3d):
        return geometry + origin
    geometry.Translate(origin)
    return geometry


def _defaults(box_x, box_y, sand_volume, grain_size, hole_diameter, lift_height):
    box_x = float(box_x or 200.0)
    box_y = float(box_y or 300.0)
    sand_volume = float(sand_volume or box_x * box_y * 40.0)
    grain_size = float(grain_size or 0.5)
    hole_diameter = float(hole_diameter or 8.0)
    lift_height = 60.0 if lift_height is None else float(lift_height)
    return box_x, box_y, sand_volume, grain_size, hole_diameter, lift_height


def _tip_name(pile):
    if pile["dent"] > 0.0:
        return "dent"
    if pile["round_r"] > 0.5:
        return "rounded"
    return "sharp"


def _info(holes, curve, params, piles):
    if not holes and curve is None:
        return "\n".join(["No points connected: flat sand, no holes."] +
                         params["warnings"])
    lines = ["holes: {}".format(len(holes))]
    if curve is not None:
        lines.append("slot curve: {:.0f} mm long".format(curve.GetLength()))
    lines += [
        "angle of repose: {:.1f} deg".format(params["angle"]),
        "fill depth: {:.1f} mm".format(params["depth"]),
        "crater depth: {:.1f} mm{}".format(
            max(params.get("crater_depths") or [params["crater_depth"]]),
            "" if params.get("time") is None or params["time"] >= params.get("t_end", 0)
            else " (now, final {:.1f})".format(params["crater_depth"])),
        "crater radius at top: {:.1f} mm".format(
            params["crater_depth"] / params["slope"] + params["hole_radius"]),
    ]
    if params.get("t_end"):
        t_end = params["t_end"]
        lines.append("flow per hole: {:.1f} cm3/s".format(
            params["flow_hole"] / 1000.0))
        lines.append("drain time: {:.1f} s".format(t_end))
        t = params.get("time")
        if t is None or t >= t_end:
            lines.append("time: finished")
        else:
            lines.append("time: {:.0f} % ({:.1f} of {:.1f} s)".format(
                100.0 * t / t_end, t, t_end))
    if piles:
        hs = [p["height"] for p in piles]
        tips = sorted(set(_tip_name(p) for p in piles))
        lines.append("pile height: {:.1f} - {:.1f} mm".format(min(hs), max(hs)))
        lines.append("drained volume: {:.0f} cm3".format(
            sum(p["volume"] for p in piles) / 1000.0))
        lines.append("pile tips: {}".format(", ".join(tips)))
    return "\n".join(lines + params["warnings"])


def sand_surface(points=None, box_x=200.0, box_y=300.0, sand_volume=None,
                 grain_size=0.5, hole_diameter=8.0, lift_height=60.0,
                 resolution=2.0, slot=None, time=None, relative=True):
    """
    Live component: sand left in the box + piles on the tray.

    points        : list of Point3d -- holes (cutout generator: 0..1 relative)
    box_x, box_y  : box size in mm
    sand_volume   : mm^3 of sand in the box (default: 40 mm fill depth)
    grain_size    : mm -> angle of repose (35 / 40 / 45 deg), flow rate
    hole_diameter : mm -> crater bottom / slot width, flow rate, jamming check
    lift_height   : mm -> box height above tray = pouring height of the piles
    resolution    : mesh grid spacing in mm
    slot          : curve -- connector slot from the cutout generator (optional)
    time          : % of completion, 0 .. 100 (empty = finished)
    relative      : bool -- True (default): points 0..1, slot in box mm coords

    Returns (sand_surface, sand_piles, hole_points, drain_curve, info).
    """
    box_x, box_y, sand_volume, grain_size, hole_diameter, lift_height = _defaults(
        box_x, box_y, sand_volume, grain_size, hole_diameter, lift_height)
    params = process_parameters(box_x, box_y, sand_volume, grain_size,
                                hole_diameter, lift_height)
    sources, holes, curve, origin, warnings = _sources_from_inputs(
        points, box_x, box_y, slot, True if relative is None else bool(relative))
    params["warnings"] += warnings
    res = max(float(resolution or 2.0), 1.0)
    crater, pile_field, piles = solve_drain(sources, box_x, box_y, params, res,
                                            time)
    box_mesh = drained_surface_mesh(crater, params)
    piles_mesh = pile_surface_mesh(pile_field, piles, params)
    piles = [p for p in piles if p]
    info = _info(holes, curve, params, piles)
    drain_curve = curve.DuplicateCurve() if curve is not None else None
    return (_to_world(box_mesh, origin), _to_world(piles_mesh, origin),
            _to_world(holes, origin), _to_world(drain_curve, origin), info)


def sand_solid(points=None, box_x=200.0, box_y=300.0, sand_volume=None,
               grain_size=0.5, hole_diameter=8.0, lift_height=60.0,
               slot=None, relative=True, run=False):
    """
    Export component: sand in the box as Brep (box minus cones / troughs).
    Same inputs as sand_surface (without resolution) plus `run` -- slow.

    Returns (sand_solid, status).
    """
    if not run:
        return [], "Toggle run to compute the Brep."
    box_x, box_y, sand_volume, grain_size, hole_diameter, lift_height = _defaults(
        box_x, box_y, sand_volume, grain_size, hole_diameter, lift_height)
    params = process_parameters(box_x, box_y, sand_volume, grain_size,
                                hole_diameter, lift_height)
    sources, holes, curve, origin, warnings = _sources_from_inputs(
        points, box_x, box_y, slot, True if relative is None else bool(relative))
    params["warnings"] += warnings
    crater, _, _ = solve_drain(sources, box_x, box_y, params, 2.0)  # crater depth
    breps, status = drained_solid_brep(sources, box_x, box_y, params)
    if breps is None:
        # fallback: closed sand mesh -> faceted Brep (always works, exact shape
        # of the live model, but many faces)
        mesh = drained_surface_mesh(crater, params, closed=True)
        brep = rg.Brep.CreateFromMesh(mesh, True)
        breps = [brep] if brep else []
        status += " Using the sand mesh as faceted Brep instead."
    return _to_world(breps, origin), "\n".join([status] + params["warnings"])


# ---------------------------------------------------------------------------
# 6. cutout generator (assignment 3) -- decides where the holes go
# ---------------------------------------------------------------------------
#
# Rule: Voronoi / Lloyd relaxation + optional connector slot.
#   * `count` random seed points in the box (inside `margin`)
#   * `relaxation` Lloyd iterations: every point moves to the centroid of its
#     Voronoi cell. 0 = random, uneven cells; ~20 = even, honeycomb-like cells.
#   * line on: two connector points (hole indices) are joined by a slot.
#     connector_collision_radius = 0: straight. > 0: the slot curves around a
#     circle of that radius at every other hole. All other points stay holes.
# The sand then reproduces this Voronoi diagram physically: every crater ridge is
# a Voronoi edge of the holes.
#
# Voronoi cells are exact: the box rectangle is clipped by the perpendicular
# bisector to every other point (half-plane clipping).


def _clip_halfplane(poly, a, b, k):
    """Keep the part of polygon `poly` where a*x + b*y <= k (Sutherland-Hodgman)."""
    out = []
    n = len(poly)
    for i, p in enumerate(poly):
        q = poly[(i + 1) % n]
        u = a * p[0] + b * p[1] - k
        v = a * q[0] + b * q[1] - k
        if u <= 0:
            out.append(p)
        if u * v < 0:
            t = u / (u - v)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _polygon_area_centroid(poly):
    a = cx = cy = 0.0
    n = len(poly)
    for i, r in enumerate(poly):
        s = poly[(i + 1) % n]
        w = r[0] * s[1] - s[0] * r[1]
        a += w
        cx += (r[0] + s[0]) * w
        cy += (r[1] + s[1]) * w
    if abs(a) < 1e-12:
        return 0.0, None
    return abs(a / 2.0), (cx / (3.0 * a), cy / (3.0 * a))


def voronoi_cells(seeds, box_x, box_y):
    """
    Exact Voronoi cells clipped to the box: start with the box rectangle and cut
    it with the perpendicular bisector to every other seed.
    Returns a list of (polygon, area, centroid) per seed.
    """
    cells = []
    for i, p in enumerate(seeds):
        poly = [(0.0, 0.0), (box_x, 0.0), (box_x, box_y), (0.0, box_y)]
        for j, q in enumerate(seeds):
            if i != j and poly:
                poly = _clip_halfplane(
                    poly, q[0] - p[0], q[1] - p[1],
                    (q[0] ** 2 + q[1] ** 2 - p[0] ** 2 - p[1] ** 2) / 2.0)
        area, centroid = _polygon_area_centroid(poly) if len(poly) >= 3 else (0.0, None)
        cells.append((poly, area, centroid or p))
    return cells


def _clamp_xy(p, box_x, box_y, margin):
    return (min(max(p[0], margin), box_x - margin),
            min(max(p[1], margin), box_y - margin))


def lloyd_points(box_x, box_y, count, seed=0, relaxation=0, margin=15.0):
    """
    Random points relaxed with Lloyd's algorithm (move every point to the
    centroid of its Voronoi cell). Returns (points, cells).
    """
    rnd = random.Random(seed)
    margin = min(margin, 0.45 * min(box_x, box_y))
    pts = [(rnd.uniform(margin, box_x - margin), rnd.uniform(margin, box_y - margin))
           for _ in range(int(count))]
    for _ in range(int(relaxation)):
        pts = [_clamp_xy(c[2], box_x, box_y, margin)
               for c in voronoi_cells(pts, box_x, box_y)]
    return pts, voronoi_cells(pts, box_x, box_y)


def _seg_dist(p, a, b):
    """Distance from point p to segment a-b (2D tuples)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den)) if den else 0.0
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _resample(path, step):
    """Evenly spaced points along a polyline (keeps both ends)."""
    seg = [math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(path, path[1:])]
    total = sum(seg)
    n = max(2, int(math.ceil(total / step)) + 1)
    out, k, acc = [], 0, 0.0
    for i in range(n):
        target = total * i / (n - 1)
        while k < len(seg) - 1 and acc + seg[k] < target:
            acc += seg[k]
            k += 1
        f = (target - acc) / seg[k] if seg[k] else 0.0
        p, q = path[k], path[k + 1]
        out.append((p[0] + f * (q[0] - p[0]), p[1] + f * (q[1] - p[1])))
    return out


def _smooth_path(path, centers, R, bounds, step=4.0, iterations=60):
    """
    Turn the taut path (tangents + polygon arcs) into a smooth line:
    resample, relax every point towards the middle of its neighbours, push it
    back out of the collision circles and into the box. Ends stay fixed.
    """
    if len(path) < 3:
        return path
    lo_x, hi_x, lo_y, hi_y = bounds
    pts = _resample(path, step)
    for _ in range(iterations):
        new = [pts[0]]
        for k in range(1, len(pts) - 1):
            x = 0.5 * pts[k][0] + 0.25 * (pts[k - 1][0] + pts[k + 1][0])
            y = 0.5 * pts[k][1] + 0.25 * (pts[k - 1][1] + pts[k + 1][1])
            for c in centers:
                dx, dy = x - c[0], y - c[1]
                d = math.hypot(dx, dy)
                if d < R:
                    if d < 1e-9:
                        dx, dy, d = 1.0, 0.0, 1.0
                    x, y = c[0] + dx / d * R, c[1] + dy / d * R
            x = min(max(x, lo_x), hi_x)
            y = min(max(y, lo_y), hi_y)
            new.append((x, y))
        new.append(pts[-1])
        pts = new
    return pts


def route_connector(pts, i, j, collision_radius, box_x, box_y, edge_margin=0.0,
                    segments=32):
    """
    Slot path from hole i to hole j.

    collision_radius = 0 : straight line.
    collision_radius > 0 : every other hole gets a collision circle of that
        radius; the path is the shortest line that stays outside all circles
        (a taut string: straight tangents + arcs hugging the circles).
        Computed as shortest path in a visibility graph over polygons that
        enclose the circles.

    Returns (path as list of (x, y), status).
    """
    import heapq
    a, b = pts[i], pts[j]
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6:
        return None, "Connector points are identical."
    R = float(collision_radius or 0.0)
    if R <= 0.0:
        return [a, b], "Straight line (collision radius 0)."

    centers = [p for k, p in enumerate(pts) if k not in (i, j)]
    # a connector point inside a circle cannot avoid it -> ignore that circle
    ignored = [c for c in centers
               if min(math.hypot(a[0] - c[0], a[1] - c[1]),
                      math.hypot(b[0] - c[0], b[1] - c[1])) < R]
    centers = [c for c in centers if c not in ignored]

    lo_x, hi_x = edge_margin, box_x - edge_margin
    lo_y, hi_y = edge_margin, box_y - edge_margin
    eps = 1e-6

    def free_point(p):
        return (lo_x - eps <= p[0] <= hi_x + eps and lo_y - eps <= p[1] <= hi_y + eps
                and all(math.hypot(p[0] - c[0], p[1] - c[1]) >= R - eps for c in centers))

    def free_segment(p, q):
        return all(_seg_dist(c, p, q) >= R - 1e-4 for c in centers)

    # polygon around each circle (vertices slightly outside, edges tangent outside)
    rv = R / math.cos(math.pi / segments) + 1e-3
    nodes = [a, b]
    for c in centers:
        for k in range(segments):
            ang = 2.0 * math.pi * k / segments
            p = (c[0] + rv * math.cos(ang), c[1] + rv * math.sin(ang))
            if free_point(p):
                nodes.append(p)

    n = len(nodes)
    dist = [float("inf")] * n
    prev = [-1] * n
    dist[0] = 0.0
    queue = [(0.0, 0)]
    done = [False] * n
    while queue:
        d, u = heapq.heappop(queue)
        if done[u]:
            continue
        done[u] = True
        if u == 1:
            break
        pu = nodes[u]
        for v in range(n):
            if done[v] or v == u:
                continue
            pv = nodes[v]
            nd = d + math.hypot(pv[0] - pu[0], pv[1] - pu[1])
            if nd < dist[v] and free_segment(pu, pv):
                dist[v], prev[v] = nd, u
                heapq.heappush(queue, (nd, v))
    if prev[1] < 0 and dist[1] == float("inf"):
        return None, ("No path around the collision circles - reduce "
                      "connector_collision_radius.")
    path, k = [], 1
    while k != -1:
        path.append(nodes[k])
        k = prev[k]
    path.reverse()
    path = _smooth_path(path, centers, R, (lo_x, hi_x, lo_y, hi_y))
    msg = "Smooth path around {} collision circle(s).".format(len(centers))
    if ignored:
        msg += " {} circle(s) ignored (connector point inside).".format(len(ignored))
    return path, msg


def _curve_xy_points(curve, spacing=2.0):
    """Vertices of a polyline curve, or samples of any other curve (2D tuples)."""
    pts = []
    try:
        ok, poly = curve.TryGetPolyline()
        if ok and poly is not None and poly.Count >= 2:
            pts = [(poly[i].X, poly[i].Y) for i in range(poly.Count)]
    except (AttributeError, TypeError):
        pts = []
    if not pts:
        n = max(2, int(math.ceil(curve.GetLength() / spacing)))
        pts = [(curve.PointAt(t).X, curve.PointAt(t).Y)
               for t in curve.DivideByCount(n, True)]
    clean = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    return clean


def slot_outline_points(path, radius, cap_segments=16):
    """
    Closed outline (2D tuples) of a slot of width 2*radius around a path:
    left offset, round end cap, right offset back, round start cap.
    Pure geometry (no Rhino offset), so it cannot fail on polylines.
    """
    n = len(path)
    if n < 2 or radius <= 0:
        return []

    def unit(dx, dy):
        ln = math.hypot(dx, dy) or 1.0
        return dx / ln, dy / ln

    dirs = [unit(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
            for i in range(n - 1)]
    left = []
    for i in range(n):
        if i == 0:
            tx, ty = dirs[0]
            scale = 1.0
        elif i == n - 1:
            tx, ty = dirs[-1]
            scale = 1.0
        else:
            tx, ty = unit(dirs[i - 1][0] + dirs[i][0], dirs[i - 1][1] + dirs[i][1])
            cos_half = max(tx * dirs[i][0] + ty * dirs[i][1], 0.5)
            scale = 1.0 / cos_half              # miter, limited to 2 x radius
        nx, ny = -ty, tx
        left.append((path[i][0] + nx * radius * scale,
                     path[i][1] + ny * radius * scale,
                     path[i][0] - nx * radius * scale,
                     path[i][1] - ny * radius * scale))

    def cap(center, direction, start_angle_vec):
        # half circle from the left side over the tip to the right side
        cx, cy = center
        ax = math.atan2(start_angle_vec[1], start_angle_vec[0])
        tip = math.atan2(direction[1], direction[0])
        sweep = (tip - ax) % (2 * math.pi)
        sweep = 2 * sweep if sweep < math.pi else -2 * (2 * math.pi - sweep)
        return [(cx + radius * math.cos(ax + sweep * k / cap_segments),
                 cy + radius * math.sin(ax + sweep * k / cap_segments))
                for k in range(1, cap_segments)]

    end_dir, start_dir = dirs[-1], dirs[0]
    out = [(l[0], l[1]) for l in left]
    out += cap(path[-1], end_dir, (-end_dir[1], end_dir[0]))
    out += [(l[2], l[3]) for l in reversed(left)]
    out += cap(path[0], (-start_dir[0], -start_dir[1]), (start_dir[1], -start_dir[0]))
    out.append(out[0])
    return out


def _slot_outline(curve, radius, tolerance=0.01):
    """Closed cut outline curve around a slot curve (at the curve's Z)."""
    if curve is None or radius <= 0:
        return None
    z = curve.PointAtStart.Z
    pts = slot_outline_points(_curve_xy_points(curve), radius)
    if len(pts) < 4:
        return None
    return rg.PolylineCurve([rg.Point3d(x, y, z) for x, y in pts])


def _two_indices(connector_points, count):
    """Panel / list / two sliders -> (i, j) or None."""
    vals = connector_points
    if vals is None:
        return None
    if not isinstance(vals, (list, tuple)):
        vals = [vals]
    out = []
    for v in vals:
        try:
            k = int(float(str(v).strip()))
        except ValueError:
            continue
        if -count <= k < count:
            out.append(k % count)
    if len(out) < 2 or out[0] == out[1]:
        return None
    return out[0], out[1]


def cutout_generator(box_x=200.0, box_y=300.0, count=12, seed=0, relaxation=5,
                     margin=15.0, line=False, connector_points=None,
                     connector_collision_radius=0.0, hole_diameter=8.0):
    """
    Component: decides the hole pattern of the perforated plate.

    box_x, box_y     : box / plate size in mm
    count            : number of holes
    seed             : random start distribution
    relaxation       : Lloyd iterations, 0 = random ... ~20 = even honeycomb
    margin           : minimum distance of holes to the wall (mm)
    line             : bool -- connect the two connector points with a slot
    connector_points : two hole indices (see labels), e.g. Panel "0" / "5"
    connector_collision_radius : mm -- 0 = straight slot. > 0: every other hole
                       gets a circle of this radius and the slot curves around
                       them (shortest path, tangent lines + arcs)
    hole_diameter    : mm -- hole and slot width

    Returns (points, slot, cut_lines, voronoi, labels, collision_circles, info)
        points    : Point3d list, relative 0..1 -- all holes except the two
                    connector points (they are the slot ends)
        slot      : slot centre curve in box mm coordinates (or None)
        cut_lines : plate outline + hole circles + slot outline, real size, Z = 0
        voronoi   : closed polylines of the Voronoi cells, Z = 0
        labels    : TextDots with the hole indices (to pick connector points)
        collision_circles : circles the slot avoids (preview)
        info      : str
    """
    box_x = float(box_x or 200.0)
    box_y = float(box_y or 300.0)
    count = max(1, int(count or 12))
    relaxation = max(0, int(relaxation or 0))
    margin = 15.0 if margin is None else float(margin)
    hole_diameter = float(hole_diameter or 8.0)
    R = max(0.0, float(connector_collision_radius or 0.0))
    r = 0.5 * hole_diameter

    pts, cells = lloyd_points(box_x, box_y, count, int(seed or 0), relaxation,
                              margin)
    areas = [c[1] for c in cells]
    status = []

    # connector slot
    slot, pair, collision_circles = None, None, []
    if line:
        pair = _two_indices(connector_points, count)
        if pair is None:
            status.append("Line on: connect two different hole indices to "
                          "connector_points.")
        else:
            path, msg = route_connector(pts, pair[0], pair[1], R, box_x, box_y,
                                        edge_margin=r)
            status.append("Slot {} -> {}: {}".format(pair[0], pair[1], msg))
            if R > 0:
                for k, (x, y) in enumerate(pts):
                    if k not in pair:
                        collision_circles.append(rg.ArcCurve(rg.Circle(
                            rg.Plane(rg.Point3d(x, y, 0.0), rg.Vector3d.ZAxis), R)))
            if path is not None:
                p3 = [rg.Point3d(x, y, 0.0) for x, y in path]
                slot = (rg.Curve.CreateInterpolatedCurve(p3, 3, rg.CurveKnotStyle.Chord)
                        if len(p3) > 3 else rg.PolylineCurve(p3))
                # slot (half width r) must not cut into another hole (radius r)
                hits = [k for k in range(count) if k not in pair and
                        min(_seg_dist(pts[k], p, q) for p, q in zip(path, path[1:]))
                        < 2.0 * r]
                if hits:
                    status.append("Warning: slot cuts into hole(s) {} - increase "
                                  "connector_collision_radius (> {:.0f} mm).".format(
                                      ", ".join(str(k) for k in hits), 2.0 * r))
            else:
                pair = None

    hole_ids = [k for k in range(count) if not (pair and k in pair)]
    points = [rg.Point3d(pts[k][0] / box_x, pts[k][1] / box_y, 0.0) for k in hole_ids]

    # cut file
    cut_lines = [rg.Rectangle3d(rg.Plane.WorldXY, box_x, box_y).ToNurbsCurve()]
    for k in hole_ids:
        cut_lines.append(rg.ArcCurve(rg.Circle(
            rg.Plane(rg.Point3d(pts[k][0], pts[k][1], 0.0), rg.Vector3d.ZAxis), r)))
    if slot is not None:
        outline = _slot_outline(slot, r)
        if outline is not None:
            cut_lines.append(outline)
        else:
            status.append("Slot outline for the cut file failed.")

    voronoi = []
    for poly, _, _ in cells:
        if len(poly) >= 3:
            voronoi.append(rg.PolylineCurve(
                [rg.Point3d(x, y, 0.0) for x, y in poly + [poly[0]]]))
    labels = [rg.TextDot(str(k), rg.Point3d(x, y, 0.0)) for k, (x, y) in enumerate(pts)]

    a_min, a_max = min(areas), max(areas)
    info = "\n".join([
        "holes: {}  |  slot: {}".format(
            len(hole_ids), "{:.0f} mm".format(slot.GetLength()) if slot else "none"),
        "relaxation: {} iterations".format(relaxation),
        "cell area: {:.0f} - {:.0f} mm2 (ratio {:.2f})".format(
            a_min, a_max, a_max / a_min if a_min else 0.0),
        "mean cell spacing: {:.0f} mm".format(math.sqrt(box_x * box_y / count)),
    ] + status)
    return points, slot, cut_lines, voronoi, labels, collision_circles, info


# ---------------------------------------------------------------------------
# 7. fabrication: pouring box as STL + instructions (assignment 3)
# ---------------------------------------------------------------------------
#
# Box = perforated bottom plate (holes / slot from the cutout generator) +
# 4 walls, optional corner legs that hold the plate exactly at lift_height.
# Inner size = box_x x box_y, inner wall height = fill depth, so the sand
# volume is exact when the box is filled flush with the wall top.

import os
import struct

SAND_BULK_DENSITY = 1.55   # g/cm3, dry sand, rough value -- weigh your own sand


def _through_cutter(curve, z_lo, height, tol=0.01):
    """Closed, outward-oriented solid from a closed planar curve, from z_lo up
    by height (used to cut openings through the plate)."""
    if curve is None or not curve.IsClosed:
        return None
    c = curve.DuplicateCurve()
    c.Translate(rg.Vector3d(0, 0, z_lo - c.PointAtStart.Z))
    brep = None
    ext = rg.Extrusion.Create(c, height, True)
    if ext is not None:
        brep = ext.ToBrep()
    if brep is None:
        region = rg.Brep.CreatePlanarBreps([c], tol)
        if region:
            brep = region[0].Faces[0].CreateExtrusion(
                rg.LineCurve(rg.Point3d(0, 0, 0), rg.Point3d(0, 0, height)), True)
    if brep is None:
        return None
    bb = brep.GetBoundingBox(True)          # extrusion may go down for CW curves
    if bb.Min.Z < z_lo - 1e-6:
        brep.Translate(rg.Vector3d(0, 0, z_lo - bb.Min.Z))
    if brep.SolidOrientation == rg.BrepSolidOrientation.Inward:
        brep.Flip()
    return brep


def _box_brep(x0, x1, y0, y1, z0, z1):
    return rg.BoundingBox(rg.Point3d(x0, y0, z0), rg.Point3d(x1, y1, z1)).ToBrep()


def _sand_type(grain_size):
    if grain_size <= 0.25:
        return "fine sand / fine Quarzsand (0.1-0.25 mm)"
    if grain_size <= 1.0:
        return "Quarzsand 0-1 mm"
    if grain_size <= 2.0:
        return "Spielsand 0-2 mm"
    if grain_size <= 5.0:
        return "Mauersand 0-5 mm"
    return "Ziegelsplitt / grit 3-16 mm"


def _mesh_brep(brep):
    meshes = rg.Mesh.CreateFromBrep(brep, rg.MeshingParameters.QualityRenderMesh)
    out = rg.Mesh()
    for m in meshes or []:
        out.Append(m)
    return out


def write_stl(mesh, path):
    """Write a mesh as binary STL (triangulates quads). Returns triangle count."""
    m = mesh.DuplicateMesh()
    m.Faces.ConvertQuadsToTriangles()
    tris = []
    for i in range(m.Faces.Count):
        f = m.Faces[i]
        a, b, c = m.Vertices[f.A], m.Vertices[f.B], m.Vertices[f.C]
        ux, uy, uz = b.X - a.X, b.Y - a.Y, b.Z - a.Z
        vx, vy, vz = c.X - a.X, c.Y - a.Y, c.Z - a.Z
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        tris.append((nx / ln, ny / ln, nz / ln, a, b, c))
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "wb") as fh:
        fh.write(b"sand pouring box - cdf material_processes_0".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for nx, ny, nz, a, b, c in tris:
            fh.write(struct.pack("<12fH", nx, ny, nz, a.X, a.Y, a.Z,
                                 b.X, b.Y, b.Z, c.X, c.Y, c.Z, 0))
    return len(tris)


def _curve_list(cut_lines):
    """GH input -> list of RhinoCommon curves (accepts item / list / Guids)."""
    if cut_lines is None:
        return []
    if not isinstance(cut_lines, (list, tuple)):
        cut_lines = [cut_lines]
    out = []
    for c in cut_lines:
        if c is not None and not hasattr(c, "IsClosed"):
            try:
                import rhinoscriptsyntax as rs
                c = rs.coercecurve(c)
            except Exception:
                c = None
        if c is not None and hasattr(c, "IsClosed"):
            out.append(c)
    return out


def _oriented(curve, clockwise):
    c = curve.DuplicateCurve()
    orient = c.ClosedCurveOrientation(rg.Vector3d.ZAxis)
    if (orient == rg.CurveOrientation.Clockwise) != clockwise:
        c.Reverse()
    return c


def pouring_box(cut_lines=None, sand_volume=None, grain_size=0.5,
                lift_height=60.0, wall=3.0, legs=True, path=None, write=False):
    """
    Component: printable pouring box, built only from the generator's cut_lines.

    cut_lines   : generator output -- plate outline (= inner box size) + hole
                  circles + slot outline. Everything except the outline is cut.
    sand_volume : mm^3 -> inner wall height = volume / inner area
    grain_size  : mm (instructions: sand type, jamming check)
    lift_height : mm, plate top (= sand base) above the tray; legs = lift - wall
    wall        : wall and plate thickness (mm), default 3
    legs        : bool -- 4 corner legs
    path        : STL file path (default: Desktop/sand_box.stl)
    write       : bool -- write the STL (Button)

    Returns (box, stl_mesh, instructions, status)
    """
    tol = 0.01
    t = float(wall or 3.0)
    legs = True if legs is None else bool(legs)
    grain_size = float(grain_size or 0.5)
    lift_height = 60.0 if lift_height is None else float(lift_height)
    status = []

    curves = [c for c in _curve_list(cut_lines) if c.IsClosed]
    if not curves:
        return [], None, "", "Connect the generator's cut_lines (Curve, List Access)."
    if len(curves) == 1 and not isinstance(cut_lines, (list, tuple)):
        return [], None, "", ("cut_lines arrives as single curves: set the input to "
                              "List Access (and remove duplicate cut_lines inputs).")

    # plate outline = largest curve -> inner box size; the rest are openings
    def bbox(c):
        return c.GetBoundingBox(True)
    curves.sort(key=lambda c: (bbox(c).Max.X - bbox(c).Min.X) *
                              (bbox(c).Max.Y - bbox(c).Min.Y))
    outline, openings = curves[-1], curves[:-1]
    ob = bbox(outline)
    x0, y0, box_x, box_y = ob.Min.X, ob.Min.Y, ob.Max.X - ob.Min.X, ob.Max.Y - ob.Min.Y
    sand_volume = float(sand_volume or box_x * box_y * 40.0)
    depth = sand_volume / (box_x * box_y)

    # hole diameter from the circles (for the instructions)
    hole_d = None
    for c in openings:
        ok, circle = c.TryGetCircle(tol)
        if ok:
            hole_d = 2.0 * circle.Radius
            break
    hole_d = hole_d or 0.0

    # print orientation: box stands on Z = 0, origin at the inner corner
    z_plate = max(lift_height - t, 0.0) if legs else 0.0
    move = rg.Vector3d(-x0, -y0, 0.0)

    def placed(c):
        d = c.DuplicateCurve()
        d.Translate(move)
        d.Translate(rg.Vector3d(0, 0, z_plate - d.PointAtStart.Z))
        return d

    outer = rg.Rectangle3d(rg.Plane(rg.Point3d(0, 0, z_plate), rg.Vector3d.ZAxis),
                           rg.Interval(-t, box_x + t),
                           rg.Interval(-t, box_y + t)).ToNurbsCurve()
    holes = [_oriented(placed(c), True) for c in openings]
    outer = _oriented(outer, False)

    # 1) planar face with inner loops, extruded
    plate, loops = None, 0
    faces = rg.Brep.CreatePlanarBreps([outer] + holes, tol)
    if faces:
        face_brep = max(faces, key=lambda b: max(f.Loops.Count for f in b.Faces))
        face = max(face_brep.Faces, key=lambda f: f.Loops.Count)
        loops = face.Loops.Count
        plate = face.CreateExtrusion(
            rg.LineCurve(rg.Point3d(0, 0, 0), rg.Point3d(0, 0, t)), True)
        if plate is not None:
            bb = plate.GetBoundingBox(True)
            if bb.Min.Z < z_plate - 1e-6:
                plate.Translate(rg.Vector3d(0, 0, z_plate - bb.Min.Z))
            if plate.SolidOrientation == rg.BrepSolidOrientation.Inward:
                plate.Flip()
    status.append("cut_lines: {} opening(s), plate loops: {} of {}".format(
        len(holes), loops, len(holes) + 1))

    # 2) missing openings -> Boolean difference, one by one
    if plate is None:
        plate = _box_brep(-t, box_x + t, -t, box_y + t, z_plate, z_plate + t)
    if loops < len(holes) + 1:
        done = 0
        for c in holes:
            cutter = _through_cutter(c, z_plate - 1.0, t + 2.0, tol)
            if cutter is None:
                continue
            diff = rg.Brep.CreateBooleanDifference(plate, cutter, tol)
            if diff:
                plate = max(diff, key=lambda b: b.GetBoundingBox(True).Diagonal.Length)
                done += 1
        status.append("Boolean fallback: {} of {} cutter(s) applied.".format(
            done, len(holes)))

    # walls + legs
    z0, z1 = z_plate + t, z_plate + t + depth
    parts = [plate,
             _box_brep(-t, box_x + t, -t, 0.0, z0, z1),
             _box_brep(-t, box_x + t, box_y, box_y + t, z0, z1),
             _box_brep(-t, 0.0, 0.0, box_y, z0, z1),
             _box_brep(box_x, box_x + t, 0.0, box_y, z0, z1)]
    leg = 3.0 * t
    if legs and z_plate > 0.0:
        for lx, ly in ((-t, -t), (box_x + t - leg, -t),
                       (-t, box_y + t - leg), (box_x + t - leg, box_y + t - leg)):
            parts.append(_box_brep(lx, lx + leg, ly, ly + leg, 0.0, z_plate))

    stl_mesh = rg.Mesh()
    for p in parts:
        stl_mesh.Append(_mesh_brep(p))
    stl_mesh.Normals.ComputeNormals()

    # preview at the sand model position: plate top at lift_height
    preview = []
    shift = rg.Vector3d(x0, y0, lift_height - (z_plate + t))
    for p in parts:
        q = p.DuplicateBrep()
        q.Translate(shift)
        preview.append(q)

    ox, oy, oz = box_x + 2 * t, box_y + 2 * t, z1
    status.append("Print size: {:.0f} x {:.0f} x {:.0f} mm".format(ox, oy, oz))
    if max(ox, oy) > 250.0:
        status.append("Warning: larger than a typical 250 mm print bed.")
    if write:
        path = path or os.path.join(os.path.expanduser("~"), "Desktop", "sand_box.stl")
        if not path.lower().endswith(".stl"):
            path += ".stl"
        n = write_stl(stl_mesh, path)
        status.append("STL written: {} ({} triangles)".format(path, n))
    else:
        status.append("Set write = True to save the STL.")

    angle = angle_from_grain_size(grain_size)
    jam_ok = hole_d >= 5.0 * grain_size if hole_d else True
    vol_cm3 = sand_volume / 1000.0
    lines = [
        "SAND POURING BOX - INSTRUCTIONS",
        "",
        "MATERIAL",
        "  Grain size: {:.2f} mm -> {}".format(grain_size, _sand_type(grain_size)),
        "  Sand must be completely DRY (humidity changes the angle).",
        "  Expected angle of repose: {:.0f} deg".format(angle),
        "  Hole / slot width {:.1f} mm >= 5 x grain ({:.1f} mm): {}".format(
            hole_d, 5 * grain_size, "OK" if jam_ok else "NO - holes will jam!"),
        "",
        "SAND AMOUNT",
        "  Volume: {:.0f} cm3  (approx. {:.0f} g at {:.2f} g/cm3)".format(
            vol_cm3, vol_cm3 * SAND_BULK_DENSITY, SAND_BULK_DENSITY),
        "  Inner wall height = fill depth = {:.1f} mm".format(depth),
        "  -> fill flush with the wall top and strike off with a ruler.",
        "",
        "POURING HEIGHT",
        "  Plate top (sand base) {:.0f} mm above the tray,".format(lift_height),
        "  plate underside {:.0f} mm.".format(max(lift_height - t, 0.0)),
        "  " + ("Legs are printed at this height - just place the box on the tray."
                if legs and z_plate > 0 else
                "No legs: hold / support the box at this height."),
        "",
        "STEPS",
        "  1. Tape the holes / slot closed from below.",
        "  2. Place the box over the tray at the pouring height.",
        "  3. Fill with sand, strike off flush with the wall top.",
        "  4. Remove the tape in one quick pull.",
        "  5. Wait until the flow stops - do not touch or shake.",
        "  6. Photograph from the top and the side (compare with the model).",
        "",
        "EXPECTED RESULT: see the info panel of the sand component.",
    ]
    return preview, stl_mesh, "\n".join(lines), "\n".join(status)
