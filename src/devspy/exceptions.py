class NoModelSetError(Exception):
    """Raised when the facade is asked to run without a model set.

    Ports DEVSJAVA's `facade.exception.NoModelSettedException`.
    """


class ModelStructureError(ValueError):
    """Raised when a coupled model is not a valid DEVS network: duplicate
    component names, couplings to unknown components or undeclared ports, or an
    input coupled straight to an output."""


class ZeroTimeLoopError(RuntimeError):
    """Raised when a simulation runs more rounds at a single instant than the
    simulator's `max_rounds_per_instant`: an illegitimate (non-progressing)
    model, typically a `ta() == 0` feedback loop."""
