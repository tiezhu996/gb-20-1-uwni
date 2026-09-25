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


def week_types_overlap(week_type1: str, week_type2: str) -> bool:
    """判断两种周次类型是否存在同一周都要上课的情况。

    每周课与任何类型都重叠；单周课与双周课错开上课，互不占用。
    """
    if week_type1 == 'weekly' or week_type2 == 'weekly':
        return True
    return week_type1 == week_type2


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
    week_type: str = 'weekly'


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
        self.classroom_usage = defaultdict(set)
        self.teacher_usage = defaultdict(set)
        self.class_usage = defaultdict(set)
        self.assignments = []
        self.conflicts = []

    @staticmethod
    def _slot_occupied(
        usage: Set[Tuple[TimeSlot, str]],
        time_slot: TimeSlot,
        week_type: str
    ) -> bool:
        """时段是否已被同周次的课程占用。

        usage 中记录 (时段, 周次类型)，单周与双周互不占用，
        每周课与任何周次类型互相占用。
        """
        if (time_slot, 'weekly') in usage or (time_slot, week_type) in usage:
            return True
        return week_type == 'weekly' and (
            (time_slot, 'odd') in usage or (time_slot, 'even') in usage
        )

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

    def is_available(
        self,
        time_slot: TimeSlot,
        week_type: str,
        teacher_id: int,
        class_id: int,
        classroom_id: int,
        teacher_available_slots: Set[TimeSlot]
    ) -> bool:
        if teacher_available_slots and time_slot not in teacher_available_slots:
            return False
        if self._slot_occupied(self.teacher_usage[teacher_id], time_slot, week_type):
            return False
        if self._slot_occupied(self.class_usage[class_id], time_slot, week_type):
            return False
        if self._slot_occupied(self.classroom_usage[classroom_id], time_slot, week_type):
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
                week_type = entry.get('week_type') or 'weekly'
                self.classroom_usage[entry['classroom_id']].add((slot, week_type))
                self.teacher_usage[entry['teacher_id']].add((slot, week_type))
                self.class_usage[entry['class_id']].add((slot, week_type))
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
                        task.week_type,
                        task.teacher_id,
                        task.class_id,
                        room,
                        teacher_available
                    ):
                        available_room = room
                        break

                if available_room:
                    self.classroom_usage[available_room].add((slot, task.week_type))
                    self.teacher_usage[task.teacher_id].add((slot, task.week_type))
                    self.class_usage[task.class_id].add((slot, task.week_type))

                    self.assignments.append({
                        'semester_id': self.semester.id,
                        'class_id': task.class_id,
                        'course_id': task.course_id,
                        'teacher_id': task.teacher_id,
                        'classroom_id': available_room,
                        'day_of_week': slot.day,
                        'period': slot.period,
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
    def _clashing_entries(entries: List[Dict]) -> List[Dict]:
        """筛选出周次重叠（同一周都要上课）而相互挤占的条目。

        单周课与双周课错开上课，即使同一时段也不算冲突。
        """
        clashing = []
        for i, entry in enumerate(entries):
            week_type = entry.get('week_type') or 'weekly'
            for j, other in enumerate(entries):
                if i == j:
                    continue
                other_week_type = other.get('week_type') or 'weekly'
                if week_types_overlap(week_type, other_week_type):
                    clashing.append(entry)
                    break
        return clashing

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
                clashing = self._clashing_entries(t_entries)
                if len(clashing) > 1:
                    conflicts.append({
                        'conflict_type': 'teacher',
                        'day_of_week': day,
                        'period': period,
                        'involved_entries': [e.get('id') for e in clashing if e.get('id')],
                        'message': f"教师 {tid} 同一时间有 {len(clashing)} 门课"
                    })

            for cid, c_entries in classroom_map.items():
                clashing = self._clashing_entries(c_entries)
                if len(clashing) > 1:
                    conflicts.append({
                        'conflict_type': 'classroom',
                        'day_of_week': day,
                        'period': period,
                        'involved_entries': [e.get('id') for e in clashing if e.get('id')],
                        'message': f"教室 {cid} 同一时间有 {len(clashing)} 门课"
                    })

            for clid, cl_entries in class_map.items():
                clashing = self._clashing_entries(cl_entries)
                if len(clashing) > 1:
                    conflicts.append({
                        'conflict_type': 'class',
                        'day_of_week': day,
                        'period': period,
                        'involved_entries': [e.get('id') for e in clashing if e.get('id')],
                        'message': f"班级 {clid} 同一时间有 {len(clashing)} 门课"
                    })

        return conflicts
