"""Daily Review: a morning business brief that only flags what is real.

Pipeline: config -> one SQL query -> same-weekday baselines -> decomposition -> persistence
checks -> brief. See docs/method.md for the reasoning behind each step.
"""

__version__ = "0.1.0"
