class NoModelSetError(Exception):
    """Raised when the facade is asked to run without a model set.

    Ports DEVSJAVA's `facade.exception.NoModelSettedException`.
    """
