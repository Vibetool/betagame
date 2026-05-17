"""
简洁地铁模拟游戏 - Mini Metro 风格
玩法:
  - 鼠标左键: 在两个站之间拖动以连接它们 (建立线路)
    - 从一个已有线路的端点站拖出可延伸该线路
    - 从空站拖到另一站会新建一条线路 (需有可用线路)
  - 鼠标右键点击某站: 删除该站所有连接 (回退用)
  - 空格: 暂停/继续
  - R: 重新开始
  - +/-: 调整游戏速度
  - 列车在线路上来回行驶, 站台到达时上下乘客
  - 任一站乘客等待超过容忍时间, 游戏结束
每隔一段时间随机新增车站; 每隔一段时间获得 1 节新车厢 或 1 条新线路 (轮换奖励)
"""

import math
import random
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pygame

# ---------- 基础配置 ----------
SCREEN_W, SCREEN_H = 1200, 760
HUD_H = 60
FPS = 60

BG_COLOR = (245, 244, 240)
HUD_BG = (255, 255, 255)
TEXT_COLOR = (40, 40, 45)
STATION_OUTLINE = (35, 35, 40)
STATION_FILL = (255, 255, 255)
PASSENGER_OUTLINE = (35, 35, 40)
DANGER_COLOR = (220, 60, 60)

# 线路颜色 (Mini Metro 调色板)
LINE_COLORS = [
    (216, 27, 27),    # red
    (32, 95, 191),    # blue
    (245, 174, 26),   # yellow
    (43, 170, 76),    # green
    (138, 80, 168),   # purple
    (28, 28, 28),     # black
    (232, 113, 35),   # orange
]

# 站点形状种类 (圆 方 三角 菱形 五边形)
SHAPES = ["circle", "square", "triangle", "diamond", "pentagon"]
SHAPE_WEIGHTS = [40, 30, 20, 7, 3]  # 罕见形状权重低

STATION_RADIUS = 16
STATION_HIT_RADIUS = 32
PASSENGER_SIZE = 6
TRAIN_LENGTH = 28
TRAIN_WIDTH = 14
TRAIN_SPEED = 170.0          # +100 提速
STATION_CAPACITY = 10        # 超过该数量 -> 进入过载倒计时
STATION_OVERLOAD_TIME = 25.0

# 站台外观
PLATFORM_LEN = 56
PLATFORM_W = 10
PLATFORM_GAP = 9             # 线路中心 -> 站台内边的距离 (侧式)
ISLAND_PLATFORM_W = 20       # 港式 (岛式) 中央站台宽度
PLATFORM_FILL = (228, 228, 232)
PLATFORM_EDGE = (90, 90, 95)
PLATFORM_SAFETY = (245, 200, 60)   # 黄色安全线

NEW_STATION_INTERVAL = 14.0
REWARD_INTERVAL = 30.0
INITIAL_LINES = 3
INITIAL_CARRIAGES = 3
TRAIN_CAPACITY_BASE = 3      # 单节车厢载客 3
CARRIAGE_CAPACITY = 3        # 附加车厢载客 3
HIGH_DENSITY_SPAWN = 6.0     # 人多区中心: 6 秒/人
LOW_DENSITY_SPAWN = 10.0     # 人少区中心: 10 秒/人

# 车厢按载客数着色 (0/1/2/3)
CAR_COLORS = [
    (96, 156, 230),   # 0 蓝
    (90, 180, 100),   # 1 绿
    (240, 200, 60),   # 2 黄
    (220, 80, 70),    # 3 红 (满)
]

# 时钟: 24 (真实) 分钟 = 1 游戏日 → 1 真实秒 = 1 游戏分钟
DAY_REAL_SECONDS = 24 * 60

# 好评
RATING_INITIAL = 100.0
RATING_BLOCK_NEW_STATION = 20.0    # 低于此值不再生成新站
RATING_PER_DELIVERY = 0.6
RATING_DROP_PER_OVERLOAD_SEC = 0.7

# 乘客流量权重 (周边进入 8 / 下站换乘 30 / 剩下出站)
FLOW_W_BOARD = 8
FLOW_W_TRANSFER = 30
FLOW_W_EXIT = 14

random.seed()


# ---------- 数据结构 ----------
@dataclass
class Zone:
    x: float
    y: float
    kind: str   # 'high' 人多 / 'low' 人少


@dataclass
class Station:
    x: float
    y: float
    shape: str
    passengers: List[str] = field(default_factory=list)
    overload_timer: float = 0.0
    spawn_timer: float = 0.0
    spawn_interval: float = 8.0
    zone_kind: str = "normal"   # 'high' / 'low' / 'normal'

    def pos(self) -> Tuple[float, float]:
        return self.x, self.y


@dataclass
class Train:
    line_idx: int
    seg_idx: int = 0       # 当前所处线段索引 (站 i -> 站 i+1)
    t: float = 0.0         # 在该段上的位置, 0..1
    direction: int = 1     # 1 向前, -1 向后
    passengers: List[str] = field(default_factory=list)
    carriages: int = 0     # 额外车厢数

    def capacity(self) -> int:
        return TRAIN_CAPACITY_BASE + self.carriages * CARRIAGE_CAPACITY


@dataclass
class Line:
    color: Tuple[int, int, int]
    stations: List[int] = field(default_factory=list)  # 站 index 列表 (有序)
    trains: List[Train] = field(default_factory=list)

    def has_station(self, s: int) -> bool:
        return s in self.stations

    def endpoints(self) -> Tuple[Optional[int], Optional[int]]:
        if not self.stations:
            return None, None
        return self.stations[0], self.stations[-1]


# ---------- 游戏主类 ----------
class MetroGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Mini Metro · 简洁地铁模拟")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Microsoft YaHei,SimHei,PingFang SC,Heiti SC,Noto Sans CJK SC,WenQuanYi Micro Hei,Arial", 18)
        self.big_font = pygame.font.SysFont("Microsoft YaHei,SimHei,PingFang SC,Heiti SC,Noto Sans CJK SC,WenQuanYi Micro Hei,Arial", 36, bold=True)
        self.reset()

    # ---- 初始化 / 重置 ----
    def reset(self):
        self.stations: List[Station] = []
        self.lines: List[Line] = []
        self.zones: List[Zone] = []
        self.available_lines = INITIAL_LINES
        self.available_carriages = 0
        self.spare_trains = 0
        self.time = 0.0
        self.spawn_station_timer = 0.0
        self.reward_timer = 0.0
        self.score = 0
        self.rating = RATING_INITIAL
        self.paused = False
        self.game_over = False
        self.speed_scale = 1.0
        self.reward_alt = 0
        # 站台形态: 'side' 线路两侧站台 / 'island' 港式岛式站台
        if not hasattr(self, "platform_style"):
            self.platform_style = "side"

        # 生成 2 人多区 + 1 人少区
        self._generate_zones()

        # 在每个区中心放一个起始站, 形状互不相同
        used_shapes: set = set()
        for z in self.zones:
            shape_choices = [sh for sh in SHAPES[:3] if sh not in used_shapes] or SHAPES[:3]
            shape = random.choice(shape_choices)
            used_shapes.add(shape)
            interval = HIGH_DENSITY_SPAWN if z.kind == "high" else LOW_DENSITY_SPAWN
            self.stations.append(Station(
                x=z.x, y=z.y, shape=shape,
                spawn_interval=interval, zone_kind=z.kind,
            ))

        # 起步给车厢
        self.available_carriages = INITIAL_CARRIAGES
        self.spare_trains = 0

    def _generate_zones(self):
        self.zones = []
        kinds = ["high", "high", "low"]
        margin_x = 220
        margin_top = HUD_H + 180
        margin_bottom = 180
        for kind in kinds:
            for _ in range(400):
                x = random.uniform(margin_x, SCREEN_W - margin_x)
                y = random.uniform(margin_top, SCREEN_H - margin_bottom)
                if all(math.hypot(z.x - x, z.y - y) > 280 for z in self.zones):
                    self.zones.append(Zone(x=x, y=y, kind=kind))
                    break
            else:
                # 找不到位置就放一个不算太苛刻的随机点
                self.zones.append(Zone(
                    x=random.uniform(margin_x, SCREEN_W - margin_x),
                    y=random.uniform(margin_top, SCREEN_H - margin_bottom),
                    kind=kind,
                ))

        # 拖拽状态
        self.drag_from_station: Optional[int] = None
        self.drag_line_idx: Optional[int] = None   # 若从端点开始延伸, 标记延伸的线
        self.drag_mouse_pos: Tuple[int, int] = (0, 0)
        self.drag_endpoint_side: int = 1  # 1 末端, -1 首端 (延伸方向)

    # ---- 站点生成 ----
    def _spawn_interval_for(self, x: float, y: float) -> Tuple[float, str]:
        """按距离区中心的反比加权, 在 6~10 秒之间渐变。"""
        if not self.zones:
            return 8.0, "normal"
        # 距离 / 类型
        weights = []
        rates = []
        for z in self.zones:
            d = math.hypot(z.x - x, z.y - y)
            weights.append(1.0 / (d + 60.0))
            rates.append(HIGH_DENSITY_SPAWN if z.kind == "high" else LOW_DENSITY_SPAWN)
        total = sum(weights)
        interval = sum(w * r for w, r in zip(weights, rates)) / total
        # 判定 zone_kind: 哪个区最近
        nearest = min(self.zones, key=lambda z: (z.x - x) ** 2 + (z.y - y) ** 2)
        nearest_d = math.hypot(nearest.x - x, nearest.y - y)
        kind = nearest.kind if nearest_d < 220 else "normal"
        return interval, kind

    def _spawn_station(self, force_basic: bool = False):
        # 好评过低不再生成新站
        if self.rating < RATING_BLOCK_NEW_STATION:
            return False
        margin = 50
        top = HUD_H + margin
        for _ in range(200):
            x = random.uniform(margin, SCREEN_W - margin)
            y = random.uniform(top, SCREEN_H - margin)
            ok = True
            for s in self.stations:
                if (s.x - x) ** 2 + (s.y - y) ** 2 < (STATION_RADIUS * 5) ** 2:
                    ok = False
                    break
            if ok:
                if force_basic:
                    shape = random.choice(SHAPES[:3])
                else:
                    shape = random.choices(SHAPES, weights=SHAPE_WEIGHTS, k=1)[0]
                interval, kind = self._spawn_interval_for(x, y)
                self.stations.append(Station(
                    x=x, y=y, shape=shape,
                    spawn_interval=interval, zone_kind=kind,
                ))
                return True
        return False

    # ---- 工具 ----
    def _station_at(self, mx: float, my: float) -> Optional[int]:
        for i, s in enumerate(self.stations):
            if (s.x - mx) ** 2 + (s.y - my) ** 2 <= STATION_HIT_RADIUS ** 2:
                return i
        return None

    def _station_orientation(self, idx: int) -> float:
        """返回经过该站的线路方向 (弧度); 没有线路时默认水平 0。"""
        s = self.stations[idx]
        for line in self.lines:
            if idx in line.stations:
                pos = line.stations.index(idx)
                if pos + 1 < len(line.stations):
                    o = self.stations[line.stations[pos + 1]]
                    return math.atan2(o.y - s.y, o.x - s.x)
                if pos - 1 >= 0:
                    o = self.stations[line.stations[pos - 1]]
                    return math.atan2(s.y - o.y, s.x - o.x)
        return 0.0

    def _line_segments(self, line: Line) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        segs = []
        for a, b in zip(line.stations, line.stations[1:]):
            segs.append((self.stations[a].pos(), self.stations[b].pos()))
        return segs

    def _seg_length(self, line: Line, idx: int) -> float:
        a = self.stations[line.stations[idx]]
        b = self.stations[line.stations[idx + 1]]
        return math.hypot(b.x - a.x, b.y - a.y)

    # ---- 输入处理 ----
    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            pygame.quit()
            sys.exit(0)
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_SPACE:
                self.paused = not self.paused
            elif ev.key == pygame.K_r:
                self.reset()
            elif ev.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.speed_scale = min(4.0, self.speed_scale + 0.25)
            elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.speed_scale = max(0.25, self.speed_scale - 0.25)
            elif ev.key == pygame.K_t:
                # 切换站台形态
                self.platform_style = "island" if self.platform_style == "side" else "side"
            elif ev.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit(0)
        if self.game_over:
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._on_left_down(ev.pos)
        elif ev.type == pygame.MOUSEMOTION:
            self.drag_mouse_pos = ev.pos
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self._on_left_up(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self._on_right_click(ev.pos)

    def _on_left_down(self, pos):
        si = self._station_at(*pos)
        if si is None:
            return
        # 是否为某条线的端点 -> 延伸该线
        for li, line in enumerate(self.lines):
            if not line.stations:
                continue
            if line.stations[0] == si:
                self.drag_from_station = si
                self.drag_line_idx = li
                self.drag_endpoint_side = -1
                self.drag_mouse_pos = pos
                return
            if line.stations[-1] == si:
                self.drag_from_station = si
                self.drag_line_idx = li
                self.drag_endpoint_side = 1
                self.drag_mouse_pos = pos
                return
        # 否则新建线路 (需要有可用线路)
        if self.available_lines > 0:
            self.drag_from_station = si
            self.drag_line_idx = None
            self.drag_endpoint_side = 1
            self.drag_mouse_pos = pos

    def _on_left_up(self, pos):
        if self.drag_from_station is None:
            return
        target = self._station_at(*pos)
        if target is None or target == self.drag_from_station:
            self.drag_from_station = None
            self.drag_line_idx = None
            return
        if self.drag_line_idx is not None:
            # 延伸已有线路
            line = self.lines[self.drag_line_idx]
            if target in line.stations:
                # 形成环路: 仅当目标是另一端点
                if (self.drag_endpoint_side == 1 and target == line.stations[0]
                        and len(line.stations) >= 3):
                    line.stations.append(target)
                elif (self.drag_endpoint_side == -1 and target == line.stations[-1]
                        and len(line.stations) >= 3):
                    line.stations.insert(0, target)
            else:
                if self.drag_endpoint_side == 1:
                    line.stations.append(target)
                else:
                    line.stations.insert(0, target)
        else:
            # 新建线路
            if self.available_lines > 0:
                color = LINE_COLORS[len(self.lines) % len(LINE_COLORS)]
                new_line = Line(color=color, stations=[self.drag_from_station, target])
                # 自动给新线路 1 列车
                new_line.trains.append(Train(line_idx=len(self.lines)))
                self.lines.append(new_line)
                self.available_lines -= 1
        self.drag_from_station = None
        self.drag_line_idx = None

    def _on_right_click(self, pos):
        si = self._station_at(*pos)
        if si is None:
            return
        # 删除所有经过该站的线路 (简化操作)
        new_lines = []
        for line in self.lines:
            if si in line.stations:
                # 回收线路
                self.available_lines += 1
                # 列车上的乘客丢回相邻站 (或丢弃)
                continue
            new_lines.append(line)
        self.lines = new_lines

    # ---- 更新 ----
    def update(self, dt: float):
        if self.paused or self.game_over:
            return
        dt *= self.speed_scale
        self.time += dt
        self.spawn_station_timer += dt
        self.reward_timer += dt

        # 新增车站
        if self.spawn_station_timer >= NEW_STATION_INTERVAL:
            self.spawn_station_timer = 0.0
            self._spawn_station()

        # 奖励
        if self.reward_timer >= REWARD_INTERVAL:
            self.reward_timer = 0.0
            if self.reward_alt == 0:
                self.available_carriages += 1
            else:
                self.available_lines += 1
            self.reward_alt = 1 - self.reward_alt

        # 站点生成乘客
        for s in self.stations:
            s.spawn_timer += dt
            if s.spawn_timer >= s.spawn_interval:
                s.spawn_timer = 0.0
                # 生成一个目的形状, 不能是本站形状
                others = [sh for sh in SHAPES if sh != s.shape]
                weights = [SHAPE_WEIGHTS[SHAPES.index(sh)] for sh in others]
                s.passengers.append(random.choices(others, weights=weights, k=1)[0])

        # 过载检测 + 好评衰减
        overloaded = 0
        for s in self.stations:
            if len(s.passengers) > STATION_CAPACITY:
                s.overload_timer += dt
                overloaded += 1
                if s.overload_timer >= STATION_OVERLOAD_TIME:
                    self.game_over = True
                    return
            else:
                s.overload_timer = max(0.0, s.overload_timer - dt * 0.5)
        if overloaded > 0:
            self.rating = max(0.0, self.rating - RATING_DROP_PER_OVERLOAD_SEC * overloaded * dt)

        # 列车运动
        for li, line in enumerate(self.lines):
            if len(line.stations) < 2:
                continue
            n_segs = len(line.stations) - 1
            # 分配可用车厢到该线列车 (简化: 玩家无需操作, 自动平均)
            self._assign_carriages_auto(line)
            for tr in line.trains:
                seg_len = self._seg_length(line, tr.seg_idx)
                if seg_len < 1e-3:
                    seg_len = 1.0
                tr.t += (TRAIN_SPEED / seg_len) * dt * tr.direction
                while tr.t >= 1.0 or tr.t <= 0.0:
                    if tr.t >= 1.0:
                        # 到达后一个站
                        arrived = line.stations[tr.seg_idx + 1]
                        self._train_visit_station(tr, line, arrived)
                        leftover = tr.t - 1.0
                        if tr.seg_idx + 1 < n_segs:
                            tr.seg_idx += 1
                            tr.t = leftover
                        else:
                            # 末端 -> 反向
                            tr.direction = -1
                            tr.t = 1.0 - leftover
                    else:  # tr.t <= 0
                        arrived = line.stations[tr.seg_idx]
                        self._train_visit_station(tr, line, arrived)
                        overflow = -tr.t
                        if tr.seg_idx > 0:
                            tr.seg_idx -= 1
                            tr.t = 1.0 - overflow
                        else:
                            tr.direction = 1
                            tr.t = overflow
                    seg_len = self._seg_length(line, tr.seg_idx)
                    if seg_len < 1e-3:
                        seg_len = 1.0

    def _assign_carriages_auto(self, line: Line):
        # 简化策略: 若有可用车厢且该线列车有未满车厢配额, 自动追加 (每列最多 +2)
        if not line.trains:
            return
        while self.available_carriages > 0:
            target = min(line.trains, key=lambda t: t.carriages)
            if target.carriages >= 2:
                break
            # 只在线路总车厢偏低时分配, 避免一次性塞完
            total = sum(t.carriages for t in line.trains)
            if total >= len(line.trains) * 2:
                break
            # 防止把全部车厢瞬间分给一条线: 这里采用低概率自动分配
            if random.random() < 0.005:
                target.carriages += 1
                self.available_carriages -= 1
            else:
                break

    def _train_visit_station(self, tr: Train, line: Line, station_idx: int):
        s = self.stations[station_idx]
        # 下客 (剩下出站): 形状匹配的乘客直接离开 -> 计分 + 加好评
        new_passengers = []
        delivered = 0
        for p in tr.passengers:
            if p == s.shape:
                self.score += 1
                delivered += 1
            else:
                new_passengers.append(p)
        tr.passengers = new_passengers
        if delivered:
            self.rating = min(100.0, self.rating + RATING_PER_DELIVERY * delivered)
        # 上客 (周边进入): 该线路能到的目的优先
        line_shapes = {self.stations[i].shape for i in line.stations}
        remaining = []
        for p in s.passengers:
            if len(tr.passengers) < tr.capacity() and p in line_shapes and p != s.shape:
                tr.passengers.append(p)
            else:
                remaining.append(p)
        s.passengers = remaining

    # ---- 绘制 ----
    def draw(self):
        self.screen.fill(BG_COLOR)
        self._draw_lines()
        self._draw_drag_preview()
        self._draw_trains()
        self._draw_stations()
        self._draw_hud()
        if self.paused and not self.game_over:
            self._draw_center_text("已暂停 (空格继续)", (60, 60, 60))
        if self.game_over:
            self._draw_center_text(f"游戏结束  送达乘客: {self.score}  按 R 重开", DANGER_COLOR)
        pygame.display.flip()

    def _draw_lines(self):
        for line in self.lines:
            if len(line.stations) < 2:
                continue
            pts = [self.stations[i].pos() for i in line.stations]
            pygame.draw.lines(self.screen, line.color, False, pts, 7)

    def _draw_drag_preview(self):
        if self.drag_from_station is None:
            return
        s = self.stations[self.drag_from_station]
        color = (180, 180, 180)
        if self.drag_line_idx is not None:
            color = self.lines[self.drag_line_idx].color
        elif self.available_lines > 0:
            color = LINE_COLORS[len(self.lines) % len(LINE_COLORS)]
        pygame.draw.line(self.screen, color, s.pos(), self.drag_mouse_pos, 5)

    def _draw_trains(self):
        for line in self.lines:
            if len(line.stations) < 2:
                continue
            for tr in line.trains:
                a = self.stations[line.stations[tr.seg_idx]]
                b = self.stations[line.stations[tr.seg_idx + 1]]
                x = a.x + (b.x - a.x) * tr.t
                y = a.y + (b.y - a.y) * tr.t
                angle = math.atan2(b.y - a.y, b.x - a.x)
                self._draw_train_shape(x, y, angle, line.color, tr)

    def _draw_train_shape(self, x, y, angle, line_color, tr: Train):
        # 主车 + 附加车厢
        bodies = 1 + tr.carriages
        gap = 4
        total_len = bodies * TRAIN_LENGTH + (bodies - 1) * gap
        start_offset = -total_len / 2 + TRAIN_LENGTH / 2
        cosA, sinA = math.cos(angle), math.sin(angle)
        total_p = len(tr.passengers)
        # slot 0 在 angle 反方向 (尾), slot bodies-1 在 angle 正方向 (头)
        # 方向 +1: 前进车头在 slot bodies-1; 方向 -1: 前进车头在 slot 0
        for slot in range(bodies):
            cx = x + cosA * (start_offset + slot * (TRAIN_LENGTH + gap))
            cy = y + sinA * (start_offset + slot * (TRAIN_LENGTH + gap))
            if tr.direction == 1:
                car_index = (bodies - 1) - slot   # slot==bodies-1 -> car 0 (车头)
            else:
                car_index = slot                  # slot==0 -> car 0
            # 前车优先填充: car 0 满了才往后
            in_car = max(0, min(3, total_p - car_index * 3))
            fill = CAR_COLORS[in_car]
            self._draw_rotated_rect(cx, cy, TRAIN_LENGTH, TRAIN_WIDTH, angle,
                                    fill, edge=line_color, edge_w=3)

    def _draw_rotated_rect(self, cx, cy, w, h, angle, color,
                           edge=(30, 30, 30), edge_w=2):
        hw, hh = w / 2, h / 2
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        cosA, sinA = math.cos(angle), math.sin(angle)
        pts = [(cx + cx_off * cosA - cy_off * sinA,
                cy + cx_off * sinA + cy_off * cosA) for cx_off, cy_off in corners]
        pygame.draw.polygon(self.screen, color, pts)
        if edge_w > 0:
            pygame.draw.polygon(self.screen, edge, pts, edge_w)

    def _draw_stations(self):
        for i, s in enumerate(self.stations):
            angle = self._station_orientation(i)
            self._draw_platforms(s, angle)
            # 过载警示环
            if s.overload_timer > 0.1:
                ratio = min(1.0, s.overload_timer / STATION_OVERLOAD_TIME)
                r = PLATFORM_GAP + PLATFORM_W + 12 + math.sin(self.time * 6) * 1.5
                pygame.draw.circle(self.screen, DANGER_COLOR,
                                   (int(s.x), int(s.y)), int(r), max(2, int(2 + ratio * 4)))
            self._draw_passengers_on_platforms(s, angle)
            self._draw_station_label(s)

    def _draw_platforms(self, s: Station, angle: float):
        if self.platform_style == "island":
            self._draw_platform_island(s, angle)
        else:
            self._draw_platform_side(s, angle)

    def _draw_platform_side(self, s: Station, angle: float):
        """形态: 线路两侧是站台"""
        cosA, sinA = math.cos(angle), math.sin(angle)
        perp_x, perp_y = -sinA, cosA
        for side in (-1, 1):
            off = side * (PLATFORM_GAP + PLATFORM_W / 2)
            cx = s.x + perp_x * off
            cy = s.y + perp_y * off
            self._draw_rotated_rect(cx, cy, PLATFORM_LEN, PLATFORM_W, angle,
                                    PLATFORM_FILL, edge=PLATFORM_EDGE, edge_w=2)
            # 站台靠线路一侧的黄色安全线
            sx = s.x + perp_x * (side * (PLATFORM_GAP + 1.5))
            sy = s.y + perp_y * (side * (PLATFORM_GAP + 1.5))
            half = PLATFORM_LEN / 2 - 4
            x1 = sx + cosA * (-half)
            y1 = sy + sinA * (-half)
            x2 = sx + cosA * half
            y2 = sy + sinA * half
            pygame.draw.line(self.screen, PLATFORM_SAFETY, (x1, y1), (x2, y2), 2)

    def _draw_platform_island(self, s: Station, angle: float):
        """形态: 港式 (岛式) 中央站台, 列车从两侧通过"""
        cosA, sinA = math.cos(angle), math.sin(angle)
        # 中央一条宽站台
        self._draw_rotated_rect(s.x, s.y, PLATFORM_LEN, ISLAND_PLATFORM_W, angle,
                                PLATFORM_FILL, edge=PLATFORM_EDGE, edge_w=2)
        perp_x, perp_y = -sinA, cosA
        # 站台两个长边各画一条黄色安全线
        half_w = ISLAND_PLATFORM_W / 2 - 2
        half_l = PLATFORM_LEN / 2 - 4
        for side in (-1, 1):
            sx = s.x + perp_x * (side * half_w)
            sy = s.y + perp_y * (side * half_w)
            x1 = sx + cosA * (-half_l)
            y1 = sy + sinA * (-half_l)
            x2 = sx + cosA * half_l
            y2 = sy + sinA * half_l
            pygame.draw.line(self.screen, PLATFORM_SAFETY, (x1, y1), (x2, y2), 2)

    def _draw_passengers_on_platforms(self, s: Station, angle: float):
        if not s.passengers:
            return
        cosA, sinA = math.cos(angle), math.sin(angle)
        perp_x, perp_y = -sinA, cosA
        spacing = PASSENGER_SIZE * 2 + 2
        per_row = max(2, int((PLATFORM_LEN - 6) // spacing))
        if self.platform_style == "island":
            # 单一中央站台, 两排乘客
            for k, p in enumerate(s.passengers):
                col = k % per_row
                row = k // per_row
                along = -PLATFORM_LEN / 2 + spacing / 2 + col * spacing
                radial = (-1 if row % 2 == 0 else 1) * (ISLAND_PLATFORM_W / 2 - PASSENGER_SIZE - 1)
                cx = s.x + cosA * along + perp_x * radial
                cy = s.y + sinA * along + perp_y * radial
                self._draw_shape(p, cx, cy, PASSENGER_SIZE, (60, 60, 65), PASSENGER_OUTLINE, 1)
            return
        # 侧式: 偶/奇分到两侧站台
        upper = [(i, p) for i, p in enumerate(s.passengers) if i % 2 == 0]
        lower = [(i, p) for i, p in enumerate(s.passengers) if i % 2 == 1]
        for group, side in ((upper, -1), (lower, 1)):
            base_off = side * (PLATFORM_GAP + PLATFORM_W / 2)
            for k, (_, p) in enumerate(group):
                col = k % per_row
                along = -PLATFORM_LEN / 2 + spacing / 2 + col * spacing
                cx = s.x + cosA * along + perp_x * base_off
                cy = s.y + sinA * along + perp_y * base_off
                self._draw_shape(p, cx, cy, PASSENGER_SIZE, (60, 60, 65), PASSENGER_OUTLINE, 1)

    def _draw_station_label(self, s: Station):
        n = len(s.passengers)
        is_full = n > STATION_CAPACITY
        color = DANGER_COLOR if is_full else TEXT_COLOR
        font = self.big_font if is_full else self.font
        # 总在屏幕上方显示, 便于读数
        label = font.render(str(n), True, color)
        y_off = -(PLATFORM_GAP + PLATFORM_W + 12)
        rect = label.get_rect(center=(int(s.x), int(s.y + y_off)))
        # 白底打底, 防止与线路重叠时看不清
        bg = pygame.Surface((rect.w + 8, rect.h + 4), pygame.SRCALPHA)
        bg.fill((255, 255, 255, 230))
        self.screen.blit(bg, (rect.x - 4, rect.y - 2))
        self.screen.blit(label, rect)

    def _draw_shape(self, shape, x, y, r, fill, outline, w):
        x, y = int(x), int(y)
        if shape == "circle":
            pygame.draw.circle(self.screen, fill, (x, y), r)
            pygame.draw.circle(self.screen, outline, (x, y), r, w)
        elif shape == "square":
            rect = pygame.Rect(x - r, y - r, r * 2, r * 2)
            pygame.draw.rect(self.screen, fill, rect)
            pygame.draw.rect(self.screen, outline, rect, w)
        elif shape == "triangle":
            pts = [(x, y - r - 1), (x - r, y + r * 0.7), (x + r, y + r * 0.7)]
            pygame.draw.polygon(self.screen, fill, pts)
            pygame.draw.polygon(self.screen, outline, pts, w)
        elif shape == "diamond":
            pts = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
            pygame.draw.polygon(self.screen, fill, pts)
            pygame.draw.polygon(self.screen, outline, pts, w)
        elif shape == "pentagon":
            pts = []
            for k in range(5):
                ang = -math.pi / 2 + k * 2 * math.pi / 5
                pts.append((x + math.cos(ang) * r, y + math.sin(ang) * r))
            pygame.draw.polygon(self.screen, fill, pts)
            pygame.draw.polygon(self.screen, outline, pts, w)

    def _draw_hud(self):
        pygame.draw.rect(self.screen, HUD_BG, (0, 0, SCREEN_W, HUD_H))
        pygame.draw.line(self.screen, (220, 220, 220), (0, HUD_H), (SCREEN_W, HUD_H), 1)
        rating_color = DANGER_COLOR if self.rating < RATING_BLOCK_NEW_STATION else TEXT_COLOR
        rating_label = f"好评: {int(self.rating)}"
        if self.rating < RATING_BLOCK_NEW_STATION:
            rating_label += " (新站已暂停)"
        style_label = "港式岛台" if self.platform_style == "island" else "两侧站台"
        txt = (f"送达: {self.score}    "
               f"可用线路: {self.available_lines}    "
               f"可用车厢: {self.available_carriages}    "
               f"车站: {len(self.stations)}    "
               f"形态: {style_label}    "
               f"速度: x{self.speed_scale:.2f}")
        self.screen.blit(self.font.render(txt, True, TEXT_COLOR), (16, 18))
        # 好评单独画一段, 满足配色需求
        r_surf = self.font.render(rating_label, True, rating_color)
        self.screen.blit(r_surf, (16, 38))
        hint = "左键拖动连线 · 端点可延伸 · 右键删除站 · T 切换形态 · 空格暂停 · +/- 调速 · R 重开"
        s = self.font.render(hint, True, (130, 130, 135))
        self.screen.blit(s, (SCREEN_W - s.get_width() - 16, 22))
        # 左下角: 时间 (24 真实分钟 = 1 游戏日, 1 真实秒 = 1 游戏分钟)
        total_min = int(self.time)
        day = total_min // (24 * 60) + 1
        hour = (total_min // 60) % 24
        minute = total_min % 60
        clock_txt = f"第 {day} 日  {hour:02d}:{minute:02d}"
        clock_surf = self.big_font.render(clock_txt, True, TEXT_COLOR)
        bg = pygame.Surface((clock_surf.get_width() + 20, clock_surf.get_height() + 8), pygame.SRCALPHA)
        bg.fill((255, 255, 255, 210))
        self.screen.blit(bg, (10, SCREEN_H - clock_surf.get_height() - 14))
        self.screen.blit(clock_surf, (20, SCREEN_H - clock_surf.get_height() - 10))

    def _draw_center_text(self, text, color):
        surf = self.big_font.render(text, True, color)
        rect = surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2))
        bg = pygame.Surface((rect.w + 40, rect.h + 20), pygame.SRCALPHA)
        bg.fill((255, 255, 255, 220))
        self.screen.blit(bg, (rect.x - 20, rect.y - 10))
        self.screen.blit(surf, rect)

    # ---- 主循环 ----
    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for ev in pygame.event.get():
                self.handle_event(ev)
            self.update(dt)
            self.draw()


if __name__ == "__main__":
    MetroGame().run()
