"""Idempotent demo seed. Runs on every container start; must be safe to repeat.

Phase 1 will add roles, permissions, settings and one demo account per role.
"""


def run() -> None:
    print("seed: nothing to seed yet (project skeleton)")


if __name__ == "__main__":
    run()
