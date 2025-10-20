import random
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Set


# ==============================
# Config / Constants
# ==============================
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_DAYS_PER_EMPLOYEE = 5
MIN_EMPLOYEES_PER_SHIFT = 2
MAX_PER_SHIFT = 2  # per-shift capacity; tweak as desired (helps trigger conflict resolution)


class Shift(Enum):
    MORNING = "Morning"
    AFTERNOON = "Afternoon"
    EVENING = "Evening"

    @staticmethod
    def parse(s: str):
        s = (s or "").strip().lower()
        if s == "morning":
            return Shift.MORNING
        if s == "afternoon":
            return Shift.AFTERNOON
        if s == "evening":
            return Shift.EVENING
        return None


# ==============================
# Domain Models
# ==============================
@dataclass
class Employee:
    name: str
    preferred_shifts_by_day: Dict[str, Shift] = field(default_factory=dict)
    days_assigned: int = 0
    days_worked: Set[str] = field(default_factory=set)

    def reset_work_counters(self):
        self.days_assigned = 0
        self.days_worked.clear()

    def can_work_day(self, day: str) -> bool:
        return (day not in self.days_worked) and (self.days_assigned < MAX_DAYS_PER_EMPLOYEE)

    def assign(self, day: str):
        self.days_worked.add(day)
        self.days_assigned += 1


@dataclass
class Schedule:
    # day -> shift -> list of employee names
    schedule: Dict[str, Dict[Shift, List[str]]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.schedule:
            for d in DAYS:
                self.schedule[d] = {sh: [] for sh in Shift}

    def clear(self):
        for d in DAYS:
            for sh in Shift:
                self.schedule[d][sh].clear()

    def has_capacity(self, day: str, shift: Shift) -> bool:
        return len(self.schedule[day][shift]) < MAX_PER_SHIFT

    def add(self, day: str, shift: Shift, employee: Employee):
        self.schedule[day][shift].append(employee.name)

    def size(self, day: str, shift: Shift) -> int:
        return len(self.schedule[day][shift])

    def names_assigned_today(self, day: str) -> Set[str]:
        acc = set()
        for sh in Shift:
            acc.update(self.schedule[day][sh])
        return acc


class Scheduler:
    def __init__(self, schedule: Schedule, employees: Dict[str, Employee]):
        self.schedule = schedule
        self.employees = employees
        self.rng = random.Random()

    def generate_weekly_schedule(self):
        carryover: List[Employee] = []

        for day_index, day in enumerate(DAYS):
            # 1) Assign employees who have a preference for this day
            todays_candidates = [e for e in self.employees.values() if day in e.preferred_shifts_by_day]
            self.rng.shuffle(todays_candidates)

            for e in todays_candidates:
                preferred = e.preferred_shifts_by_day.get(day)
                self._attempt_assign_with_conflict_resolution(e, day, preferred, carryover, day_index)

            # 2) Try to place carryover employees into this day (any shift)
            if carryover:
                self.rng.shuffle(carryover)
                still = []
                for e in carryover:
                    if e.can_work_day(day) and self._try_any_shift_today(e, day):
                        continue
                    still.append(e)
                carryover = still

            # 3) Ensure minimum staffing per shift with random fill
            self._ensure_minimum_staffing(day)

        # Remaining carryover cannot be placed further (end of week)

    def _attempt_assign_with_conflict_resolution(self, e: Employee, day: str, preferred: Shift,
                                                 carryover: List[Employee], day_index: int):
        if not e.can_work_day(day):
            self._push_to_next_day_if_possible(e, carryover, day_index)
            return

        # Try preferred shift first
        if preferred and self.schedule.has_capacity(day, preferred):
            self.schedule.add(day, preferred, e)
            e.assign(day)
            return

        # Preferred full -> try other shifts same day
        for alt in list(Shift):
            if alt == preferred:
                continue
            if self.schedule.has_capacity(day, alt) and e.can_work_day(day):
                self.schedule.add(day, alt, e)
                e.assign(day)
                return

        # Still can't place -> push to next day
        self._push_to_next_day_if_possible(e, carryover, day_index)

    def _push_to_next_day_if_possible(self, e: Employee, carryover: List[Employee], day_index: int):
        if day_index < len(DAYS) - 1 and e.days_assigned < MAX_DAYS_PER_EMPLOYEE:
            carryover.append(e)

    def _try_any_shift_today(self, e: Employee, day: str) -> bool:
        shifts = list(Shift)
        self.rng.shuffle(shifts)
        for sh in shifts:
            if self.schedule.has_capacity(day, sh):
                self.schedule.add(day, sh, e)
                e.assign(day)
                return True
        return False

    def _ensure_minimum_staffing(self, day: str):
        # Keep filling until each shift has at least MIN_EMPLOYEES_PER_SHIFT or no eligible people remain
        for sh in Shift:
            while self.schedule.size(day, sh) < MIN_EMPLOYEES_PER_SHIFT:
                already = self.schedule.names_assigned_today(day)
                eligible = [
                    e for e in self.employees.values()
                    if e.can_work_day(day) and (e.name not in already)
                ]
                if not eligible:
                    break  # cannot fill further
                pick = self.rng.choice(eligible)
                if self.schedule.has_capacity(day, sh):
                    self.schedule.add(day, sh, pick)
                    pick.assign(day)
                else:
                    break


# ==============================
# UI / Console Helpers
# ==============================
def pad_right(s: str, width: int) -> str:
    s = s or ""
    if len(s) >= width:
        return s
    return s + " " * (width - len(s))


def print_schedule_table(sched: Schedule):
    # Compute column widths
    day_col_w = max(len("Day"), max(len(d) for d in DAYS))
    names_by_day_shift: Dict[str, Dict[Shift, str]] = {d: {} for d in DAYS}

    col_w = {
        Shift.MORNING: len("Morning"),
        Shift.AFTERNOON: len("Afternoon"),
        Shift.EVENING: len("Evening"),
    }

    for d in DAYS:
        for sh in Shift:
            joined = ", ".join(sched.schedule[d][sh])
            names_by_day_shift[d][sh] = joined
            col_w[sh] = max(col_w[sh], len(joined))

    header = (
        f"{pad_right('Day', day_col_w)} | "
        f"{pad_right('Morning', col_w[Shift.MORNING])} | "
        f"{pad_right('Afternoon', col_w[Shift.AFTERNOON])} | "
        f"{pad_right('Evening', col_w[Shift.EVENING])}"
    )
    print("\n" + header)
    print("-" * len(header))

    for d in DAYS:
        line = (
            f"{pad_right(d, day_col_w)} | "
            f"{pad_right(names_by_day_shift[d][Shift.MORNING], col_w[Shift.MORNING])} | "
            f"{pad_right(names_by_day_shift[d][Shift.AFTERNOON], col_w[Shift.AFTERNOON])} | "
            f"{pad_right(names_by_day_shift[d][Shift.EVENING], col_w[Shift.EVENING])}"
        )
        print(line)

    # Warnings for understaffed shifts
    warnings = []
    for d in DAYS:
        for sh in Shift:
            sz = len(sched.schedule[d][sh])
            if sz < MIN_EMPLOYEES_PER_SHIFT:
                warnings.append(f"{d} {sh.value} shift has only {sz} employee(s).")
    if warnings:
        print("\n⚠ Warnings:")
        for w in warnings:
            print(" - " + w)
    print()


def input_employees(employees: Dict[str, Employee]):
    print("\nEnter employee names (type 'done' when finished):")
    while True:
        name = input("Employee name: ").strip()
        if name.lower() == "done":
            break
        if not name:
            print("Name cannot be empty.")
            continue

        if name in employees:
            print("Employee already exists. Updating their preferences.")
            emp = employees[name]
        else:
            emp = Employee(name=name)

        print(
            f"Enter preferred shift per day for {name} as one of: morning / afternoon / evening / none"
        )
        for day in DAYS:
            while True:
                pref = input(f"  {day} preference: ").strip().lower()
                shift = Shift.parse(pref)
                if shift is not None or pref in ("none", ""):
                    if shift is None:
                        # None/blank means no preference / not available -> remove any existing
                        emp.preferred_shifts_by_day.pop(day, None)
                    else:
                        emp.preferred_shifts_by_day[day] = shift
                    break
                else:
                    print("Please enter 'morning', 'afternoon', 'evening', or 'none'.")

        employees[name] = emp
        print(f"Saved preferences for: {name}\n")

    print(f"Employee entry complete. Total employees: {len(employees)}")


def main():
    employees: Dict[str, Employee] = {}
    schedule = Schedule()
    scheduler = Scheduler(schedule, employees)
    schedule_generated = False

    while True:
        print()
        print("=================================")
        print(" Employee Scheduling Application")
        print("=================================")
        print("1. Enter Employees and Preferences")
        print("2. Generate Weekly Schedule")
        print("3. View Weekly Schedule")
        print("4. Exit")
        print("=================================")
        choice = input("Enter your choice: ").strip()

        if choice == "1":
            input_employees(employees)
            schedule_generated = False

        elif choice == "2":
            if not employees:
                print("No employees found. Please enter employees first (option 1).")
                continue
            # reset schedule/counters and generate anew
            schedule.clear()
            for e in employees.values():
                e.reset_work_counters()
            scheduler.generate_weekly_schedule()
            schedule_generated = True
            print("Schedule generated.")

        elif choice == "3":
            if not schedule_generated:
                print("No schedule generated yet. Choose option 2 to generate.")
                continue
            print_schedule_table(schedule)

        elif choice == "4":
            print("Goodbye!")
            break

        else:
            print("Invalid choice. Please pick 1-4.")


if __name__ == "__main__":
    main()
