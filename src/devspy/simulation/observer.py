from __future__ import annotations

import copy
from typing import Any, Iterable

from devspy.modeling.devs import Bag


class Observer:
    """Receives the λ and δ events of a simulation; override what you need.

    Attach with `DevsSuiteFacade.add_observer` (or append to a simulator's
    `observers`). With no observer attached the kernel pays one emptiness check
    per transition and per output.
    """

    def on_output(self, t: float, model: Any, y: Bag) -> None:
        """`model`'s λ produced the non-empty bag `y` at time `t`."""

    def on_transition(self, t: float, model: Any, kind: str, e: float, x: Bag) -> None:
        """`model` just took a transition at time `t`: `kind` is "int", "ext" or
        "con", `e` the elapsed time passed to it (for "int", the time since its
        last transition) and `x` its input bag ({} for "int")."""


# Model attributes that are network structure, not state: never snapshotted.
_STRUCTURE = frozenset({"name", "_parent", "_inports", "_outports", "_simulator"})


def model_state(model: Any) -> dict:
    try:
        attrs = vars(model)
    except TypeError:
        raise TypeError(f"cannot snapshot {model!r}: models need a __dict__") from None
    return {k: v for k, v in attrs.items() if k not in _STRUCTURE}


def set_model_state(model: Any, state: dict) -> None:
    attrs = vars(model)
    for k in [k for k in attrs if k not in _STRUCTURE and k not in state]:
        del attrs[k]
    attrs.update(state)


def deepcopy_keeping(state: Any, keep: Iterable[Any]) -> Any:
    """Deep-copy `state`, but keep the objects in `keep` (models, digraphs,
    simulators) by reference, so a model that points at another model does not
    drag a copy of the whole network along."""
    return copy.deepcopy(state, {id(obj): obj for obj in keep})
