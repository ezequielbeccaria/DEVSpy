from devspy import Atomic, Content, Digraph, IntEnt, Message, Pair
from devspy.modeling.digraph import Couprel


class Source(Atomic):
    def __init__(self) -> None:
        super().__init__("src")
        self.add_outport("out")

    def initialize(self) -> None:
        self.hold_in("emit", 1.0)

    def deltint(self) -> None:
        self.passivate()

    def out(self) -> Message:
        m = Message()
        m.add(Content("out", IntEnt(7)))
        return m


class Sink(Atomic):
    def __init__(self) -> None:
        super().__init__("sink")
        self.add_inport("in")
        self.seen: list[int] = []

    def initialize(self) -> None:
        self.seen = []
        self.passivate()

    def deltext(self, e: float, x: Message) -> None:
        for c in x:
            if c.get_port_name() == "in":
                self.seen.append(int(c.get_value()))


def test_couprel_add_translate_remove():
    cr = Couprel()
    src = Pair("a", "out")
    dst = Pair("b", "in")
    cr.add(src, dst)
    assert dst in cr.translate("a", "out")
    cr.remove(src, dst)
    assert not cr.translate("a", "out")


def test_digraph_composition_and_coupling():
    g = Digraph("root")
    s = Source()
    k = Sink()
    g.add(s)
    g.add(k)
    g.add_coupling(s, "out", k, "in")

    assert g.with_name("src") is s
    assert g.with_name("sink") is k
    assert s.get_parent() is g

    couprel_pairs = list(g.get_couprel().iter_pairs())
    assert (Pair("src", "out"), Pair("sink", "in")) in couprel_pairs


def test_digraph_check_name_uniqueness():
    g = Digraph("root")
    s = Source()
    g.add(s)
    assert g.check_name_uniqueness("new") is True
    assert g.check_name_uniqueness("src") is False
