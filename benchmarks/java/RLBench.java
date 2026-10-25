import GenCol.intEnt;
import facade.DevsSuiteFacade;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import model.modeling.atomic;
import model.modeling.content;
import model.modeling.digraph;
import model.modeling.message;

// RL-environment-shaped benchmark for DEVSJAVA. Mirrors ../rl_model.py exactly.
// usage: java RLBench SECTIONS EPISODES HORIZON   (prints one JSON line)
public class RLBench {
    static long episodeSeed, decisions, reward;

    static long lcg(long x) { return (x * 1103515245L + 12345L) % 2147483648L; }

    static class Section extends atomic {
        int idx; long rng; int last;
        Section(int idx) { super("S" + idx); this.idx = idx; addInport("act"); addOutport("obs"); }
        public void initialize() { rng = lcg(episodeSeed * 7919 + idx + 1); last = 0; travel(); }
        void travel() { rng = lcg(rng); last = 1 + (int) ((rng >> 16) % 5); holdIn("travel", last); }
        public void deltint() { if (phaseIs("travel")) passivateIn("wait"); else travel(); }
        public void deltext(double e, message x) {
            for (int i = 0; i < x.getLength(); i++) {
                int v = ((intEnt) x.getValOnPort("act", i)).getv();
                if (v / 10 == idx && phaseIs("wait")) { holdIn("dwell", v % 10); return; }
            }
            Continue(e);
        }
        public message out() {
            message m = new message();
            if (phaseIs("travel")) m.add(new content("obs", new intEnt(idx * 1000 + last)));
            return m;
        }
        public void showState() {}
    }

    static class Agent extends atomic {
        long rng; List<Integer> pending = new ArrayList<>();
        Agent() { super("agent"); addInport("obs"); addOutport("act"); }
        public void initialize() { rng = lcg(episodeSeed + 424242); pending = new ArrayList<>(); passivate(); }
        public void deltext(double e, message x) {
            int[] obs = new int[x.getLength()];
            for (int i = 0; i < obs.length; i++) obs[i] = ((intEnt) x.getValOnPort("obs", i)).getv();
            Arrays.sort(obs);
            for (int o : obs) {
                int idx = o / 1000, travel = o % 1000;
                reward += 3 - Math.abs(travel - 3);
                decisions++;
                rng = lcg(rng);
                int dwell = (int) ((travel + (rng >> 16) % 2) % 4);
                pending.add(idx * 10 + dwell);
            }
            holdIn("act", 0.0);
        }
        public void deltint() { pending = new ArrayList<>(); passivate(); }
        public message out() {
            message m = new message();
            for (int a : pending) m.add(new content("act", new intEnt(a)));
            return m;
        }
        public void showState() {}
    }

    static digraph build(int sections) {
        digraph g = new digraph("rl_env");
        Agent agent = new Agent();
        g.add(agent);
        for (int i = 0; i < sections; i++) {
            Section s = new Section(i);
            g.add(s);
            g.addCoupling(s, "obs", agent, "obs");
            g.addCoupling(agent, "act", s, "act");
        }
        return g;
    }

    public static void main(String[] a) throws Exception {
        int m = Integer.parseInt(a[0]), episodes = Integer.parseInt(a[1]);
        double horizon = Double.parseDouble(a[2]);
        long t0 = System.nanoTime();
        DevsSuiteFacade facade = new DevsSuiteFacade(build(m));
        long t1 = System.nanoTime();
        double[] ep = new double[episodes];
        for (int i = 0; i < episodes; i++) {
            long s = System.nanoTime();
            episodeSeed = i;
            facade.reset();
            facade.simulateToTime(horizon);
            ep[i] = (System.nanoTime() - s) / 1e6;
        }
        long t2 = System.nanoTime();
        double first = ep[0];
        Arrays.sort(ep);
        System.out.printf(Locale.ROOT,
            "{\"engine\": \"devsjava\", \"sections\": %d, \"episodes\": %d, \"horizon\": %.1f, \"decisions\": %d, \"reward\": %d, \"build_ms\": %f, \"run_ms\": %f, \"first_ep_ms\": %f, \"ep_ms_median\": %f}%n",
            m, episodes, horizon, decisions, reward, (t1 - t0) / 1e6, (t2 - t1) / 1e6, first, ep[episodes / 2]);
    }
}
