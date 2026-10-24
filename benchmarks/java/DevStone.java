import GenCol.intEnt;
import facade.DevsSuiteFacade;
import model.modeling.atomic;
import model.modeling.content;
import model.modeling.digraph;
import model.modeling.message;

// DEVStone-LI-like benchmark for DEVSJAVA (Devs-Suite-Facade). Mirrors ../devstone_model.py.
// usage: java DevStone WIDTH DEPTH EVENTS REPS   (prints one JSON line)
public class DevStone {
    static long nInt, nExt, nSink;

    static class Gen extends atomic {
        int n, k;
        Gen(int n) { super("gen"); addOutport("out"); this.n = n; }
        public void initialize() { k = 0; holdIn("active", 1.0); }
        public void deltint() { nInt++; k++; if (k >= n) passivate(); else holdIn("active", 1.0); }
        public void deltext(double e, message x) {}
        public message out() { message m = new message(); m.add(new content("out", new intEnt(k))); return m; }
        public void showState() {}
    }

    static class Proc extends atomic {
        int count;
        Proc(String name) { super(name); addInport("in"); addOutport("out"); }
        public void initialize() { count = 0; passivate(); }
        public void deltext(double e, message x) {
            nExt++;
            for (int i = 0; i < x.getLength(); i++) if (messageOnPort(x, "in", i)) count++;
            if (phaseIs("passive")) holdIn("active", 0.1); else Continue(e);
        }
        public void deltint() { nInt++; passivate(); }
        public message out() { message m = new message(); m.add(new content("out", new intEnt(count))); return m; }
        public void showState() {}
    }

    static class Sink extends atomic {
        Sink() { super("sink"); addInport("in"); }
        public void initialize() { passivate(); }
        public void deltext(double e, message x) { nExt++; nSink += x.getLength(); passivate(); }
        public message out() { return new message(); }
        public void showState() {}
    }

    static digraph level(int width, int depth) {
        digraph g = new digraph("L" + depth);
        g.addInport("in");
        g.addOutport("out");
        int np = depth > 1 ? width - 1 : width;
        Proc first = null;
        for (int i = 0; i < np; i++) {
            Proc p = new Proc("P" + depth + "_" + i);
            if (first == null) first = p;
            g.add(p);
            g.addCoupling(g, "in", p, "in");
        }
        g.addCoupling(first, "out", g, "out");
        if (depth > 1) {
            digraph sub = level(width, depth - 1);
            g.add(sub);
            g.addCoupling(g, "in", sub, "in");
            g.addCoupling(sub, "out", g, "out");
        }
        return g;
    }

    static digraph build(int w, int d, int n) {
        digraph top = new digraph("top");
        Gen gen = new Gen(n); Sink sink = new Sink(); digraph lv = level(w, d);
        top.add(gen); top.add(lv); top.add(sink);
        top.addCoupling(gen, "out", lv, "in");
        top.addCoupling(lv, "out", sink, "in");
        return top;
    }

    public static void main(String[] a) throws Exception {
        int w = Integer.parseInt(a[0]), d = Integer.parseInt(a[1]), n = Integer.parseInt(a[2]), reps = Integer.parseInt(a[3]);
        StringBuilder b = new StringBuilder(), sm = new StringBuilder();
        for (int r = 0; r < reps; r++) {
            nInt = nExt = nSink = 0;
            long t0 = System.nanoTime();
            DevsSuiteFacade f = new DevsSuiteFacade(build(w, d, n));
            f.reset();
            long t1 = System.nanoTime();
            f.simulateToTime(1e18);
            long t2 = System.nanoTime();
            b.append(r > 0 ? "," : "").append((t1 - t0) / 1e6);
            sm.append(r > 0 ? "," : "").append((t2 - t1) / 1e6);
        }
        System.out.printf(java.util.Locale.ROOT,
            "{\"engine\": \"devsjava\", \"w\": %d, \"d\": %d, \"n\": %d, \"int\": %d, \"ext\": %d, \"sink\": %d, \"build_ms\": [%s], \"sim_ms\": [%s]}%n",
            w, d, n, nInt, nExt, nSink, b, sm);
    }
}
