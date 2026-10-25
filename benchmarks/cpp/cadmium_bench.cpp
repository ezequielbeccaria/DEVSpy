// Cadmium v2 (github.com/SimulationEverywhere/cadmium_v2) ports of
// ../devstone_model.py and ../rl_model.py. Hierarchical coordinators (no flattening).
// usage: cadmium_bench devstone W D N REPS | cadmium_bench rl SECTIONS EPISODES HORIZON
// Default confluentTransition is internal(); external(0) (neutral for these models).
// RootCoordinator::simulate(dt) runs while tNext < tLast + dt, so rl passes horizon + eps.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <limits>
#include <string>
#include <vector>
#include <cadmium/core/modeling/atomic.hpp>
#include <cadmium/core/modeling/coupled.hpp>
#include <cadmium/core/simulation/root_coordinator.hpp>

using namespace cadmium;
static const double INF = std::numeric_limits<double>::infinity();
static long long nInt, nExt, nSink, decisions, reward, episodeSeed;

static double now_ms() {
    using namespace std::chrono;
    return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}

// --- DEVStone-like -------------------------------------------------------------
struct GenState { int k = 0; double sigma = 1.0; };
std::ostream &operator<<(std::ostream &o, const GenState &s) { return o << s.k; }
struct Gen : Atomic<GenState> {
    Port<int> out; int n;
    explicit Gen(int n) : Atomic<GenState>("gen", GenState()), n(n) { out = addOutPort<int>("out"); }
    void internalTransition(GenState &s) const override { nInt++; s.k++; s.sigma = s.k >= n ? INF : 1.0; }
    void externalTransition(GenState &, double) const override {}
    void output(const GenState &s) const override { out->addMessage(s.k); }
    [[nodiscard]] double timeAdvance(const GenState &s) const override { return s.sigma; }
};

struct ProcState { int count = 0; bool active = false; double sigma = INF; };
std::ostream &operator<<(std::ostream &o, const ProcState &s) { return o << s.count; }
struct Proc : Atomic<ProcState> {
    Port<int> in, out;
    explicit Proc(const std::string &id) : Atomic<ProcState>(id, ProcState()) {
        in = addInPort<int>("in"); out = addOutPort<int>("out");
    }
    void externalTransition(ProcState &s, double e) const override {
        nExt++;
        s.count += (int)in->getBag().size();
        if (!s.active) { s.active = true; s.sigma = 0.1; } else if (s.sigma < INF) s.sigma -= e;
    }
    void internalTransition(ProcState &s) const override { nInt++; s.active = false; s.sigma = INF; }
    void output(const ProcState &s) const override { out->addMessage(s.count); }
    [[nodiscard]] double timeAdvance(const ProcState &s) const override { return s.sigma; }
};

struct SinkState { int dummy = 0; };
std::ostream &operator<<(std::ostream &o, const SinkState &) { return o; }
struct Sink : Atomic<SinkState> {
    Port<int> in;
    Sink() : Atomic<SinkState>("sink", SinkState()) { in = addInPort<int>("in"); }
    void externalTransition(SinkState &, double) const override { nExt++; nSink += (long long)in->getBag().size(); }
    void internalTransition(SinkState &) const override {}
    void output(const SinkState &) const override {}
    [[nodiscard]] double timeAdvance(const SinkState &) const override { return INF; }
};

struct Level : Coupled {
    Level(int w, int d) : Coupled("L" + std::to_string(d)) {
        auto in = addInPort<int>("in");
        auto out = addOutPort<int>("out");
        int np = d > 1 ? w - 1 : w;
        for (int i = 0; i < np; i++) {
            auto p = addComponent<Proc>("P" + std::to_string(d) + "_" + std::to_string(i));
            addCoupling(in, p->in);
            if (i == 0) addCoupling(p->out, out);
        }
        if (d > 1) {
            auto sub = addComponent<Level>(w, d - 1);
            addCoupling(in, sub->getInPort("in"));
            addCoupling(sub->getOutPort("out"), out);
        }
    }
};

struct DevStoneTop : Coupled {
    DevStoneTop(int w, int d, int n) : Coupled("top") {
        auto gen = addComponent<Gen>(n);
        auto lv = addComponent<Level>(w, d);
        auto sink = addComponent<Sink>();
        addCoupling(gen->out, lv->getInPort("in"));
        addCoupling(lv->getOutPort("out"), sink->in);
    }
};

// --- RL-shaped --------------------------------------------------------------------
static long long lcg(long long x) { return (x * 1103515245LL + 12345LL) % 2147483648LL; }

struct SecState { long long rng = 0; int last = 0, phase = 0; double sigma = INF; };  // 0 travel 1 wait 2 dwell
std::ostream &operator<<(std::ostream &o, const SecState &s) { return o << s.phase; }
static void travel(SecState &s) { s.rng = lcg(s.rng); s.last = 1 + (int)((s.rng >> 16) % 5); s.phase = 0; s.sigma = s.last; }
static SecState secInit(int idx) { SecState s; s.rng = lcg(episodeSeed * 7919 + idx + 1); travel(s); return s; }
struct Section : Atomic<SecState> {
    Port<int> act, obs; int idx;
    explicit Section(int idx) : Atomic<SecState>("S" + std::to_string(idx), secInit(idx)), idx(idx) {
        act = addInPort<int>("act"); obs = addOutPort<int>("obs");
    }
    void internalTransition(SecState &s) const override { if (s.phase == 0) { s.phase = 1; s.sigma = INF; } else travel(s); }
    void externalTransition(SecState &s, double e) const override {
        for (int v : act->getBag()) {
            if (v / 10 == idx && s.phase == 1) { s.phase = 2; s.sigma = v % 10; return; }
        }
        if (s.sigma < INF) s.sigma -= e;
    }
    void output(const SecState &s) const override { if (s.phase == 0) obs->addMessage(idx * 1000 + s.last); }
    [[nodiscard]] double timeAdvance(const SecState &s) const override { return s.sigma; }
};

struct AgentState { long long rng = 0; std::vector<int> pending; double sigma = INF; };
std::ostream &operator<<(std::ostream &o, const AgentState &s) { return o << s.pending.size(); }
static AgentState agentInit() { AgentState s; s.rng = lcg(episodeSeed + 424242); return s; }
struct Agent : Atomic<AgentState> {
    Port<int> obs, act;
    Agent() : Atomic<AgentState>("agent", agentInit()) { obs = addInPort<int>("obs"); act = addOutPort<int>("act"); }
    void externalTransition(AgentState &s, double) const override {
        std::vector<int> o = obs->getBag();
        std::sort(o.begin(), o.end());
        for (int v : o) {
            int idx = v / 1000, tr = v % 1000;
            reward += 3 - std::abs(tr - 3);
            decisions++;
            s.rng = lcg(s.rng);
            s.pending.push_back(idx * 10 + (int)((tr + (s.rng >> 16) % 2) % 4));
        }
        s.sigma = 0.0;
    }
    void internalTransition(AgentState &s) const override { s.pending.clear(); s.sigma = INF; }
    void output(const AgentState &s) const override { for (int a : s.pending) act->addMessage(a); }
    [[nodiscard]] double timeAdvance(const AgentState &s) const override { return s.sigma; }
};

struct RLEnv : Coupled {
    explicit RLEnv(int m) : Coupled("rl_env") {
        auto agent = addComponent<Agent>();
        for (int i = 0; i < m; i++) {
            auto s = addComponent<Section>(i);
            addCoupling(s->obs, agent->obs);
            addCoupling(agent->act, s->act);
        }
    }
};

int main(int argc, char **argv) {
    std::string kind = argv[1];
    if (kind == "devstone") {
        int w = atoi(argv[2]), d = atoi(argv[3]), n = atoi(argv[4]), reps = atoi(argv[5]);
        std::string b, s;
        for (int r = 0; r < reps; r++) {
            nInt = nExt = nSink = 0;
            double t0 = now_ms();
            auto top = std::make_shared<DevStoneTop>(w, d, n);
            double t1 = now_ms();
            auto root = RootCoordinator(top);
            root.start();
            root.simulate(INF);
            root.stop();
            double t2 = now_ms();
            b += (r ? "," : "") + std::to_string(t1 - t0);
            s += (r ? "," : "") + std::to_string(t2 - t1);
        }
        printf("{\"engine\": \"cadmium\", \"w\": %d, \"d\": %d, \"n\": %d, \"int\": %lld, \"ext\": %lld, "
               "\"sink\": %lld, \"build_ms\": [%s], \"sim_ms\": [%s]}\n", w, d, n, nInt, nExt, nSink,
               b.c_str(), s.c_str());
    } else {
        int m = atoi(argv[2]), episodes = atoi(argv[3]);
        double horizon = atof(argv[4]);
        std::vector<double> ep;
        double t1 = now_ms();
        for (int e = 0; e < episodes; e++) {
            double s = now_ms();
            episodeSeed = e;
            auto root = RootCoordinator(std::make_shared<RLEnv>(m));
            root.start();
            root.simulate(horizon + 1e-9);
            root.stop();
            ep.push_back(now_ms() - s);
        }
        double t2 = now_ms(), first = ep[0];
        std::sort(ep.begin(), ep.end());
        printf("{\"engine\": \"cadmium\", \"sections\": %d, \"episodes\": %d, \"horizon\": %.1f, "
               "\"decisions\": %lld, \"reward\": %lld, \"build_ms\": 0.0, \"run_ms\": %f, "
               "\"first_ep_ms\": %f, \"ep_ms_median\": %f}\n", m, episodes, horizon, decisions, reward,
               t2 - t1, first, ep[episodes / 2]);
    }
}
