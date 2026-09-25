import random
from typing import List, Dict, Tuple, Set, Optional
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class TimeSlot:
    day: int
    period: int

    def __hash__(self):
        return hash((self.day, self.period))

    def __eq__(self, other):
        return self.day == other.day and self.period == other.period


def week_patterns_conflict(pattern1: str, pattern2: str) -> bool:
    """判断两种周次安排是否在同一时段撞车。

    每周课与任何课冲突；单周课与双周课互不占用；同周次的课冲突。
    """
    if pattern1 == 'weekly' or pattern2 == 'weekly':
        return True
    return pattern1 == pattern2


@dataclass
class SchedulingTask:
    class_id: int
    course_id: int
    teacher_id: int
    weekly_hours: int
    preferred_room_type: str
    priority: str
    available_time_slots: List[TimeSlot]
    classroom_capacity: int
    week_pattern: str = 'weekly'


class CSPScheduler:
    def __init__(self, semester):
        self.semester = semester
        self.weekly_days = semester.weekly_days
        self.daily_periods = len(semester.daily_periods) if semester.daily_periods else 7
        self.all_slots = [
            TimeSlot(day=d + 1, period=p + 1)
            for d in range(self.weekly_days)
            for p in range(self.daily_periods)
        ]
        # 资源占用：资源 id -> TimeSlot -> 该时段已占用的周次集合
        # 同一时段可同时被一门单周课和一门双周课占用
        self.classroom_usage = defaultdict(lambda: defaultdict(set))
        self.teacher_usage = defaultdict(lambda: defaultdict(set))
        self.class_usage = defaultdict(lambda: defaultdict(set))
        self.assignments = []
        self.conflicts = []

    def generate_time_slots_for_priority(self, priority: str) -> List[TimeSlot]:
        morning_periods = min(4, self.daily_periods)
        morning_slots = [
            s for s in self.all_slots
            if s.period <= morning_periods
        ]
        afternoon_slots = [
            s for s in self.all_slots
            if s.period > morning_periods
        ]

        if priority == 'high':
            return morning_slots + afternoon_slots
        elif priority == 'medium':
            return random.sample(self.all_slots, len(self.all_slots))
        else:
            return afternoon_slots + morning_slots

    def _slot_free(
        self,
        usage: Dict[int, Dict[TimeSlot, Set[str]]],
        resource_id: int,
        time_slot: TimeSlot,
        week_pattern: str
    ) -> bool:
        patterns = usage[resource_id].get(time_slot)
        if not patterns:
            return True
        return not any(
            week_patterns_conflict(week_pattern, p) for p in patterns
        )

    def _mark_used(
        self,
        usage: Dict[int, Dict[TimeSlot, Set[str]]],
        resource_id: int,
        time_slot: TimeSlot,
        week_pattern: str
    ) -> None:
        usage[resource_id][time_slot].add(week_pattern)

    def is_available(
        self,
        time_slot: TimeSlot,
        teacher_id: int,
        class_id: int,
        classroom_id: int,
        teacher_available_slots: Set[TimeSlot],
        week_pattern: str = 'weekly'
    ) -> bool:
        if teacher_available_slots and time_slot not in teacher_available_slots:
            return False
        if not self._slot_free(self.teacher_usage, teacher_id, time_slot, week_pattern):
            return False
        if not self._slot_free(self.class_usage, class_id, time_slot, week_pattern):
            return False
        if not self._slot_free(self.classroom_usage, classroom_id, time_slot, week_pattern):
            return False
        return True

    def get_compatible_classrooms(
        self,
        preferred_room_type: str,
        required_capacity: int,
        classrooms_data: Dict[int, Dict]
    ) -> List[int]:
        compatible = []
        for cid, cdata in classrooms_data.items():
            if cdata['room_type'] == preferred_room_type and cdata['capacity'] >= required_capacity:
                compatible.append(cid)
        if not compatible:
            for cid, cdata in classrooms_data.items():
                if cdata['capacity'] >= required_capacity:
                    compatible.append(cid)
        return compatible

    def schedule(
        self,
        tasks: List[SchedulingTask],
        classrooms_data: Dict[int, Dict],
        teachers_data: Dict[int, Dict],
        locked_entries: Optional[List[Dict]] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        self.assignments = []
        self.conflicts = []
        self.classroom_usage.clear()
        self.teacher_usage.clear()
        self.class_usage.clear()

        if locked_entries:
            for entry in locked_entries:
                slot = TimeSlot(day=entry['day_of_week'], period=entry['period'])
                pattern = entry.get('week_pattern', 'weekly')
                self._mark_used(self.classroom_usage, entry['classroom_id'], slot, pattern)
                self._mark_used(self.teacher_usage, entry['teacher_id'], slot, pattern)
                self._mark_used(self.class_usage, entry['class_id'], slot, pattern)
                self.assignments.append(entry)

        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        sorted_tasks = sorted(
            tasks,
            key=lambda t: (priority_order[t.priority], -t.weekly_hours)
        )

        for task in sorted_tasks:
            hours_assigned = 0
            teacher_available = set()
            if teachers_data.get(task.teacher_id, {}).get('available_time_slots'):
                for slot_dict in teachers_data[task.teacher_id]['available_time_slots']:
                    teacher_available.add(
                        TimeSlot(day=slot_dict['day'], period=slot_dict['period'])
                    )

            compatible_rooms = self.get_compatible_classrooms(
                task.preferred_room_type,
                task.classroom_capacity,
                classrooms_data
            )

            if not compatible_rooms:
                self.conflicts.append({
                    'type': 'classroom',
                    'task': f"班级{task.class_id}的{task.course_id}",
                    'message': f"没有找到适合 {task.preferred_room_type} 类型的教室"
                })
                continue

            candidate_slots = self.generate_time_slots_for_priority(task.priority)

            attempts = 0
            while hours_assigned < task.weekly_hours and attempts < 500:
                attempts += 1
                slot = random.choice(candidate_slots)
                available_room = None

                for room in compatible_rooms:
                    if self.is_available(
                        slot,
                        task.teacher_id,
                        task.class_id,
                        room,
                        teacher_available,
                        task.week_pattern
                    ):
                        available_room = room
                        break

                if available_room:
                    self._mark_used(self.classroom_usage, available_room, slot, task.week_pattern)
                    self._mark_used(self.teacher_usage, task.teacher_id, slot, task.week_pattern)
                    self._mark_used(self.class_usage, task.class_id, slot, task.week_pattern)

                    self.assignments.append({
                        'semester_id': self.semester.id,
                        'class_id': task.class_id,
                        'course_id': task.course_id,
                        'teacher_id': task.teacher_id,
                        'classroom_id': available_room,
                        'day_of_week': slot.day,
                        'period': slot.period,
                        'week_pattern': task.week_pattern,
                        'is_locked': False
                    })
                    hours_assigned += 1

            if hours_assigned < task.weekly_hours:
                self.conflicts.append({
                    'type': 'insufficient_slots',
                    'task': f"班级{task.class_id}的{task.course_id}",
                    'message': f"仅安排了 {hours_assigned}/{task.weekly_hours} 课时"
                })

        return self.assignments, self.conflicts


class ConflictDetector:
    @staticmethod
    def _conflicting_groups(entries: List[Dict]) -> List[List[Dict]]:
        """按周次口径拆分同一时段占用同一资源的课程。

        每周课与任何课撞车；单周课与双周课互不占用；同周次的课撞车。
        """
        weekly = [e for e in entries if e.get('week_pattern', 'weekly') == 'weekly']
        odd = [e for e in entries if e.get('week_pattern') == 'odd']
        even = [e for e in entries if e.get('week_pattern') == 'even']

        groups = []
        if weekly:
            if len(entries) > 1:
                groups.append(entries)
        else:
            if len(odd) > 1:
                groups.append(odd)
            if len(even) > 1:
                groups.append(even)
        return groups

    def detect_conflicts(self, entries: List[Dict]) -> List[Dict]:
        conflicts = []
        by_slot = defaultdict(list)

        for entry in entries:
            key = (entry['day_of_week'], entry['period'])
            by_slot[key].append(entry)

        for (day, period), slot_entries in by_slot.items():
            teacher_map = defaultdict(list)
            classroom_map = defaultdict(list)
            class_map = defaultdict(list)

            for entry in slot_entries:
                teacher_map[entry['teacher_id']].append(entry)
                classroom_map[entry['classroom_id']].append(entry)
                class_map[entry['class_id']].append(entry)

            for tid, t_entries in teacher_map.items():
                for group in self._conflicting_groups(t_entries):
                    conflicts.append({
                        'conflict_type': 'teacher',
                        'day_of_week': day,
                        'period': period,
                        'involved_entries': [e.get('id') for e in group if e.get('id')],
                        'message': f"教师 {tid} 同一时间有 {len(group)} 门课"
                    })

            for cid, c_entries in classroom_map.items():
                for group in self._conflicting_groups(c_entries):
                    conflicts.append({
                        'conflict_type': 'classroom',
                        'day_of_week': day,
                        'period': period,
                        'involved_entries': [e.get('id') for e in group if e.get('id')],
                        'message': f"教室 {cid} 同一时间有 {len(group)} 门课"
                    })

            for clid, cl_entries in class_map.items():
                for group in self._conflicting_groups(cl_entries):
                    conflicts.append({
                        'conflict_type': 'class',
                        'day_of_week': day,
                        'period': period,
                        'involved_entries': [e.get('id') for e in group if e.get('id')],
                        'message': f"班级 {clid} 同一时间有 {len(group)} 门课"
                    })

        return conflicts
