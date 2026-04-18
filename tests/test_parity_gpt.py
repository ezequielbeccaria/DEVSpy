from examples.gpt_model import run


def test_gpt_produces_expected_arrivals_and_completions():
    trans = run(end_time=30.0)

    # Generator emits every 2s starting at t=2 until Transducer sends stop at t=20.
    expected_arrivals = [
        (2.0, 1), (4.0, 2), (6.0, 3), (8.0, 4), (10.0, 5),
        (12.0, 6), (14.0, 7), (16.0, 8), (18.0, 9), (20.0, 10),
    ]
    got_arrivals = [(round(t, 6), j) for t, j in trans.arrivals]
    assert got_arrivals == expected_arrivals

    # Processor takes 3s and drops arrivals while busy, so only odd jobs complete:
    # job 1 at t=5, job 3 at t=9, job 5 at t=13, job 7 at t=17, job 9 at t=21.
    expected_completions = [(5.0, 1), (9.0, 3), (13.0, 5), (17.0, 7), (21.0, 9)]
    got_completions = [(round(t, 6), j) for t, j in trans.completions]
    assert got_completions == expected_completions
