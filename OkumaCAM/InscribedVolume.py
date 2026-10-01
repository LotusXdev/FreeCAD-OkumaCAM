"""OkumaCAM Inscribed Volume Geometry Engine.

Detects Maximum Inscribed Rectangles (MIR) and Largest Inscribed Circles (LIC)
within arbitrary 2D pocket boundaries to allow hybrid roughing using Okuma
OSP canned cycles (PMIL, PMILR, circular pocketing) and parametric subroutines.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


@dataclass
class InscribedRectangle:
    """Represents a Maximum Inscribed Rectangle."""
    xp: float
    yp: float
    idx: float
    jdy: float
    angle_deg: float = 0.0
    width: float = 0.0
    height: float = 0.0
    area: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0


@dataclass
class InscribedCircle:
    """Represents a Largest Inscribed Circle."""
    center_x: float
    center_y: float
    radius: float
    area: float = 0.0


@dataclass
class InscribedResult:
    """Result of inscribed volume analysis on a pocket boundary."""
    strategy: str  # "RECTANGLE", "CIRCLE", or "NONE"
    total_area: float
    inscribed_area: float
    coverage_ratio: float
    rectangle: Optional[InscribedRectangle] = None
    circle: Optional[InscribedCircle] = None
    residual_polygons: List[List[Tuple[float, float]]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class InscribedVolumeAnalyzer:
    """Geometric analyzer for finding inscribed canned-cycle volumes inside 2D contours."""

    @staticmethod
    def polygon_area(points: Sequence[Tuple[float, float]]) -> float:
        """Calculate the signed area of a 2D polygon using the Shoelace formula."""
        n = len(points)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]
        return 0.5 * area

    @staticmethod
    def point_in_polygon(
        x: float,
        y: float,
        boundary: Sequence[Tuple[float, float]],
        holes: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
    ) -> bool:
        """Test if point (x, y) is inside the boundary and outside all holes (ray-casting)."""
        inside = False
        n = len(boundary)
        if n < 3:
            return False

        p1x, p1y = boundary[0]
        for i in range(n + 1):
            p2x, p2y = boundary[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        if not inside:
            return False

        if holes:
            for hole in holes:
                if InscribedVolumeAnalyzer.point_in_polygon(x, y, hole):
                    return False

        return True

    @staticmethod
    def distance_to_segment(
        px: float, py: float, ax: float, ay: float, bx: float, by: float
    ) -> float:
        """Shortest distance from point (px, py) to line segment (ax, ay)-(bx, by)."""
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-12:
            return math.hypot(px - ax, py - ay)

        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    @classmethod
    def point_to_polygon_distance(
        cls,
        px: float,
        py: float,
        boundary: Sequence[Tuple[float, float]],
        holes: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
    ) -> float:
        """Signed distance from point to polygon boundary (positive inside, negative outside)."""
        is_inside = cls.point_in_polygon(px, py, boundary, holes)

        min_dist = float("inf")
        n = len(boundary)
        for i in range(n):
            ax, ay = boundary[i]
            bx, by = boundary[(i + 1) % n]
            d = cls.distance_to_segment(px, py, ax, ay, bx, by)
            if d < min_dist:
                min_dist = d

        if holes:
            for hole in holes:
                hn = len(hole)
                for i in range(hn):
                    ax, ay = hole[i]
                    bx, by = hole[(i + 1) % hn]
                    d = cls.distance_to_segment(px, py, ax, ay, bx, by)
                    if d < min_dist:
                        min_dist = d

        return min_dist if is_inside else -min_dist

    @classmethod
    def find_largest_inscribed_circle(
        cls,
        boundary: Sequence[Tuple[float, float]],
        holes: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
        tolerance: float = 0.2,
    ) -> InscribedCircle:
        """Find the Largest Inscribed Circle using the Pole of Inaccessibility (PIA) algorithm.

        Args:
            boundary: 2D polygon vertices.
            holes: Optional inner boundary loops.
            tolerance: Convergence precision in mm.

        Returns:
            InscribedCircle dataclass with center_x, center_y, radius, and area.
        """
        if len(boundary) < 3:
            return InscribedCircle(0.0, 0.0, 0.0, 0.0)

        min_x = min(p[0] for p in boundary)
        max_x = max(p[0] for p in boundary)
        min_y = min(p[1] for p in boundary)
        max_y = max(p[1] for p in boundary)

        width = max_x - min_x
        height = max_y - min_y
        cell_size = min(width, height)
        if cell_size <= 0.0:
            return InscribedCircle(0.0, 0.0, 0.0, 0.0)

        h = cell_size / 2.0

        cx = sum(p[0] for p in boundary) / len(boundary)
        cy = sum(p[1] for p in boundary) / len(boundary)
        best_d = cls.point_to_polygon_distance(cx, cy, boundary, holes)
        best_x, best_y = cx, cy

        pq: List[Tuple[float, float, float, float, float]] = []

        x = min_x
        while x < max_x:
            y = min_y
            while y < max_y:
                mid_x = x + h
                mid_y = y + h
                d = cls.point_to_polygon_distance(mid_x, mid_y, boundary, holes)
                if d > best_d:
                    best_d = d
                    best_x, best_y = mid_x, mid_y
                max_d = d + h * math.sqrt(2.0)
                heapq.heappush(pq, (-max_d, -d, mid_x, mid_y, h))
                y += cell_size
            x += cell_size

        iterations = 0
        max_iterations = 2000
        while pq and iterations < max_iterations:
            iterations += 1
            neg_max_d, neg_d, cell_x, cell_y, cell_h = heapq.heappop(pq)
            max_d = -neg_max_d
            d = -neg_d

            if d > best_d:
                best_d = d
                best_x, best_y = cell_x, cell_y

            if max_d - best_d <= tolerance:
                continue

            sub_h = cell_h / 2.0
            for dx, dy in ((-sub_h, -sub_h), (-sub_h, sub_h), (sub_h, -sub_h), (sub_h, sub_h)):
                nx = cell_x + dx
                ny = cell_y + dy
                sub_d = cls.point_to_polygon_distance(nx, ny, boundary, holes)
                if sub_d > best_d:
                    best_d = sub_d
                    best_x, best_y = nx, ny
                sub_max_d = sub_d + sub_h * math.sqrt(2.0)
                if sub_max_d > best_d + tolerance:
                    heapq.heappush(pq, (-sub_max_d, -sub_d, nx, ny, sub_h))

        radius = max(0.0, best_d)
        area = math.pi * radius * radius
        return InscribedCircle(best_x, best_y, radius, area)

    @classmethod
    def _rotate_points(
        cls, points: Sequence[Tuple[float, float]], angle_rad: float
    ) -> List[Tuple[float, float]]:
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return [(x * cos_a - y * sin_a, x * sin_a + y * cos_a) for x, y in points]

    @classmethod
    def _find_max_axis_aligned_rectangle(
        cls,
        boundary: Sequence[Tuple[float, float]],
        holes: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
        grid_resolution: float = 1.0,
    ) -> Tuple[float, float, float, float, float]:
        """Find Maximum Inscribed Rectangle aligned with current axes using histogram sweep."""
        min_x = min(p[0] for p in boundary)
        max_x = max(p[0] for p in boundary)
        min_y = min(p[1] for p in boundary)
        max_y = max(p[1] for p in boundary)

        w = max_x - min_x
        h = max_y - min_y
        if w <= 0 or h <= 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0

        res_x = max(grid_resolution, w / 80.0)
        res_y = max(grid_resolution, h / 80.0)

        num_cols = int(math.ceil(w / res_x)) + 1
        num_rows = int(math.ceil(h / res_y)) + 1

        grid = []
        for r in range(num_rows):
            y_val = min_y + r * res_y
            row = []
            for c in range(num_cols):
                x_val = min_x + c * res_x
                inside = cls.point_in_polygon(x_val, y_val, boundary, holes)
                row.append(1 if inside else 0)
            grid.append(row)

        heights = [0] * num_cols
        best_area = 0.0
        best_rect = (0.0, 0.0, 0.0, 0.0, 0.0)

        for r in range(num_rows):
            for c in range(num_cols):
                if grid[r][c] == 1:
                    heights[c] += 1
                else:
                    heights[c] = 0

            stack: List[int] = []
            for c in range(num_cols + 1):
                cur_h = heights[c] if c < num_cols else 0
                while stack and heights[stack[-1]] >= cur_h:
                    h_idx = stack.pop()
                    rect_h_blocks = heights[h_idx]
                    rect_w_blocks = c if not stack else (c - stack[-1] - 1)
                    
                    real_w = rect_w_blocks * res_x
                    real_h = rect_h_blocks * res_y
                    area = real_w * real_h

                    if area > best_area:
                        best_area = area
                        left_col = stack[-1] + 1 if stack else 0
                        top_row = r - rect_h_blocks + 1
                        xp = min_x + left_col * res_x
                        yp = min_y + top_row * res_y
                        best_rect = (xp, yp, real_w, real_h, area)
                stack.append(c)

        return best_rect

    @classmethod
    def find_maximum_inscribed_rectangle(
        cls,
        boundary: Sequence[Tuple[float, float]],
        holes: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
        angle_step_deg: float = 15.0,
        grid_resolution: float = 1.0,
    ) -> InscribedRectangle:
        """Find the Maximum Inscribed Rectangle across tested orientation angles."""
        if len(boundary) < 3:
            return InscribedRectangle(0.0, 0.0, 0.0, 0.0)

        angles = {0.0}
        n = len(boundary)
        for i in range(n):
            p1 = boundary[i]
            p2 = boundary[(i + 1) % n]
            edge_angle = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])) % 90.0
            angles.add(round(edge_angle, 1))

        if angle_step_deg > 0:
            cur = 0.0
            while cur < 90.0:
                angles.add(cur)
                cur += angle_step_deg

        best_area = -1.0
        best_rec = InscribedRectangle(0.0, 0.0, 0.0, 0.0)

        for ang in sorted(angles):
            rad = math.radians(ang)
            rot_poly = cls._rotate_points(boundary, -rad)
            rot_holes = [cls._rotate_points(h, -rad) for h in holes] if holes else None

            xp_rot, yp_rot, rw, rh, area = cls._find_max_axis_aligned_rectangle(
                rot_poly, rot_holes, grid_resolution=grid_resolution
            )

            if area > best_area:
                best_area = area
                center_rot_x = xp_rot + rw / 2.0
                center_rot_y = yp_rot + rh / 2.0
                
                cx = center_rot_x * math.cos(rad) - center_rot_y * math.sin(rad)
                cy = center_rot_x * math.sin(rad) + center_rot_y * math.cos(rad)

                if abs(ang) < 1e-4:
                    best_rec = InscribedRectangle(
                        xp=xp_rot,
                        yp=yp_rot,
                        idx=rw,
                        jdy=rh,
                        angle_deg=0.0,
                        width=rw,
                        height=rh,
                        area=area,
                        center_x=cx,
                        center_y=cy,
                    )
                else:
                    best_rec = InscribedRectangle(
                        xp=cx - rw / 2.0,
                        yp=cy - rh / 2.0,
                        idx=rw,
                        jdy=rh,
                        angle_deg=ang,
                        width=rw,
                        height=rh,
                        area=area,
                        center_x=cx,
                        center_y=cy,
                    )

        return best_rec

    @classmethod
    def analyze_pocket(
        cls,
        boundary: Sequence[Tuple[float, float]],
        tool_diameter: float,
        finish_allowance: float = 0.5,
        min_coverage: float = 0.40,
        holes: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
    ) -> InscribedResult:
        """Analyze an arbitrary pocket boundary to determine optimal roughing strategy."""
        total_area = abs(cls.polygon_area(boundary))
        if holes:
            for h in holes:
                total_area -= abs(cls.polygon_area(h))

        if total_area <= 0.0:
            return InscribedResult(
                strategy="NONE",
                total_area=0.0,
                inscribed_area=0.0,
                coverage_ratio=0.0,
            )

        # 1. Evaluate Maximum Inscribed Rectangle
        rec = cls.find_maximum_inscribed_rectangle(boundary, holes)
        rec_eligible = (
            rec.width >= 1.2 * tool_diameter and rec.height >= 1.2 * tool_diameter
        )
        rec_cov = (rec.area / total_area) if rec_eligible else 0.0

        # 2. Evaluate Largest Inscribed Circle
        circ = cls.find_largest_inscribed_circle(boundary, holes)
        circ_eligible = (circ.radius * 2.0) >= 1.2 * tool_diameter
        circ_cov = (circ.area / total_area) if circ_eligible else 0.0

        best_cov = max(rec_cov, circ_cov)

        if best_cov >= min_coverage:
            if rec_cov >= circ_cov:
                strategy = "RECTANGLE"
                inscribed_area = rec.area
            else:
                strategy = "CIRCLE"
                inscribed_area = circ.area
        else:
            strategy = "NONE"
            inscribed_area = 0.0

        residuals = cls._compute_residuals(boundary, rec if strategy == "RECTANGLE" else None, circ if strategy == "CIRCLE" else None)

        return InscribedResult(
            strategy=strategy,
            total_area=total_area,
            inscribed_area=inscribed_area,
            coverage_ratio=best_cov if strategy != "NONE" else 0.0,
            rectangle=rec if strategy == "RECTANGLE" else None,
            circle=circ if strategy == "CIRCLE" else None,
            residual_polygons=residuals,
            metadata={
                "tool_diameter": tool_diameter,
                "finish_allowance": finish_allowance,
                "min_coverage": min_coverage,
                "rec_coverage": rec_cov,
                "circ_coverage": circ_cov,
            },
        )

    @classmethod
    def _compute_residuals(
        cls,
        boundary: Sequence[Tuple[float, float]],
        rec: Optional[InscribedRectangle],
        circ: Optional[InscribedCircle],
    ) -> List[List[Tuple[float, float]]]:
        """Compute residual polygons outside the inscribed core geometry."""
        residuals = []
        if not rec and not circ:
            return [list(boundary)]

        if rec and abs(rec.angle_deg) < 1e-3:
            rx1 = rec.xp
            rx2 = rec.xp + rec.idx
            ry1 = rec.yp
            ry2 = rec.yp + rec.jdy

            corner_cluster: List[Tuple[float, float]] = []
            for px, py in boundary:
                if px < rx1 - 1e-3 or px > rx2 + 1e-3 or py < ry1 - 1e-3 or py > ry2 + 1e-3:
                    corner_cluster.append((px, py))
                else:
                    if len(corner_cluster) >= 3:
                        residuals.append(corner_cluster)
                    corner_cluster = []
            if len(corner_cluster) >= 3:
                residuals.append(corner_cluster)

        return residuals

    @classmethod
    def generate_residual_clearing_commands(
        cls,
        boundary: Optional[Sequence[Tuple[float, float]]] = None,
        rec: Optional[InscribedRectangle] = None,
        circ: Optional[InscribedCircle] = None,
        tool_diameter: float = 10.0,
        stepover_ratio: float = 0.70,
        feedrate: float = 250.0,
        residual_polygons: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
    ) -> List[Tuple[str, Dict[str, float]]]:
        """Generate 2D cutting commands (G0/G1) to clear residual margin volumes.

        Computes the volume outside the inscribed core rectangle or circle and emits
        raster clearing toolpath segments.
        """
        commands: List[Tuple[str, Dict[str, float]]] = []
        tool_radius = tool_diameter / 2.0
        stepover = max(1.0, tool_diameter * stepover_ratio)

        # If boundary is provided and core is specified, subtract core intervals directly
        if boundary and (rec or circ):
            min_y = min(p[1] for p in boundary)
            max_y = max(p[1] for p in boundary)

            y = min_y + tool_radius
            direction = 1

            while y <= max_y - tool_radius + 1e-4:
                # 1. Find X-intersections with outer boundary
                intersections: List[float] = []
                n = len(boundary)
                for i in range(n):
                    p1 = boundary[i]
                    p2 = boundary[(i + 1) % n]
                    if (p1[1] <= y < p2[1]) or (p2[1] <= y < p1[1]):
                        if abs(p2[1] - p1[1]) > 1e-6:
                            x_int = p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1])
                            intersections.append(x_int)

                intersections.sort()
                raw_intervals: List[Tuple[float, float]] = []
                for j in range(0, len(intersections) - 1, 2):
                    raw_intervals.append((intersections[j], intersections[j + 1]))

                # 2. Subtract inscribed core interval from raw intervals
                valid_intervals: List[Tuple[float, float]] = []
                for x_start, x_end in raw_intervals:
                    if rec and abs(rec.angle_deg) < 1e-3:
                        ry1 = rec.yp
                        ry2 = rec.yp + rec.jdy
                        rx1 = rec.xp
                        rx2 = rec.xp + rec.idx

                        if ry1 <= y <= ry2:
                            # Left piece
                            if rx1 > x_start + tool_diameter:
                                valid_intervals.append((x_start + tool_radius, min(x_end - tool_radius, rx1)))
                            # Right piece
                            if rx2 < x_end - tool_diameter:
                                valid_intervals.append((max(x_start + tool_radius, rx2), x_end - tool_radius))
                        else:
                            if x_start + tool_radius < x_end - tool_radius:
                                valid_intervals.append((x_start + tool_radius, x_end - tool_radius))

                    elif circ:
                        cy = circ.center_y
                        cx = circ.center_x
                        r = circ.radius
                        dy = abs(y - cy)
                        if dy < r:
                            dx = math.sqrt(r * r - dy * dy)
                            cx1 = cx - dx
                            cx2 = cx + dx
                            # Left piece
                            if cx1 > x_start + tool_diameter:
                                valid_intervals.append((x_start + tool_radius, min(x_end - tool_radius, cx1)))
                            # Right piece
                            if cx2 < x_end - tool_diameter:
                                valid_intervals.append((max(x_start + tool_radius, cx2), x_end - tool_radius))
                        else:
                            if x_start + tool_radius < x_end - tool_radius:
                                valid_intervals.append((x_start + tool_radius, x_end - tool_radius))
                    else:
                        if x_start + tool_radius < x_end - tool_radius:
                            valid_intervals.append((x_start + tool_radius, x_end - tool_radius))

                # 3. Emit motion commands
                for xs, xe in valid_intervals:
                    if xs < xe:
                        if direction == 1:
                            commands.append(("G0", {"X": round(xs, 4), "Y": round(y, 4)}))
                            commands.append(("G1", {"X": round(xe, 4), "Y": round(y, 4), "F": feedrate}))
                        else:
                            commands.append(("G0", {"X": round(xe, 4), "Y": round(y, 4)}))
                            commands.append(("G1", {"X": round(xs, 4), "Y": round(y, 4), "F": feedrate}))

                direction = -direction
                y += stepover

            return commands

        # Fallback to residual polygons if passed
        if residual_polygons:
            for poly in residual_polygons:
                if len(poly) < 3:
                    continue
                min_x = min(p[0] for p in poly)
                max_x = max(p[0] for p in poly)
                min_y = min(p[1] for p in poly)
                max_y = max(p[1] for p in poly)

                y = min_y + tool_radius
                direction = 1
                while y <= max_y - tool_radius + 1e-4:
                    intersections = []
                    n = len(poly)
                    for i in range(n):
                        p1 = poly[i]
                        p2 = poly[(i + 1) % n]
                        if (p1[1] <= y < p2[1]) or (p2[1] <= y < p1[1]):
                            if abs(p2[1] - p1[1]) > 1e-6:
                                x_int = p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1])
                                intersections.append(x_int)
                    intersections.sort()
                    for j in range(0, len(intersections) - 1, 2):
                        x_start = intersections[j] + tool_radius
                        x_end = intersections[j + 1] - tool_radius
                        if x_start < x_end:
                            if direction == 1:
                                commands.append(("G0", {"X": round(x_start, 4), "Y": round(y, 4)}))
                                commands.append(("G1", {"X": round(x_end, 4), "Y": round(y, 4), "F": feedrate}))
                            else:
                                commands.append(("G0", {"X": round(x_end, 4), "Y": round(y, 4)}))
                                commands.append(("G1", {"X": round(x_start, 4), "Y": round(y, 4), "F": feedrate}))
                    direction = -direction
                    y += stepover

        return commands
