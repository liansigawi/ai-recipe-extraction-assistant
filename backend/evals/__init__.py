"""Quality evaluations that call the real model. Never part of the software tests (tests/).

They cost money and depend on the model's answers, so they run only when you start them,
with a fixed, small number of requests. See run_extraction.py.
"""
