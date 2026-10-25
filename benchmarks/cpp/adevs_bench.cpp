// adevs (github.com/smiz/adevs) ports of ../devstone_model.py and ../rl_model.py.
// usage: adevs_bench devstone W D N REPS | adevs_bench rl SECTIONS EPISODES HORIZON
// adevs flattens Coupled models into one Graph and uses a heap scheduler.
// delta_conf has no e argument; here it is delta_int(); delta_ext(0, xb), which is
// neutral for these models (see ../FINDINGS.md).
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>
#include <vector>
#include "adevs/adevs.h"

using Atomic = adevs::Atomic<int, double>;
using Coupled = adevs::Coupled<int, double>;
using PinValue = adevs::PinValue<int>;
using Simulator = adevs::Simulator<int, double>;
using pin_t = adevs::pin_t;
using List = std::list<PinValue>;
static const double INF = adevs_inf<double>();
static long long nInt, nExt, nSink, decisions, reward, episodeSeed;

static double now_ms() {
    using namespace std::chrono;
    return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}

// --- DEVStone-like -------------------------------------------------------------
struct Gen : Atomic {
    pin_t out; int n, k = 0; double sigma = 1.0;
    explicit Gen(int n) : n(n) {}
    double ta() override { return sigma; }
    void delta_int() override { nInt++; k++; sigma = k >= n ? INF : 1.0; }
    void delta_ext(double, List const &) override {}
    void delta_conf(List const &xb) override { delta_int(); delta_ext(0, xb); }
    void output_func(List &yb) override { yb.push_back(PinValue(out, k)); }
};

struct Proc : Atomic {
    pin_t in, out; int count = 0; double sigma = INF; bool active = false;
    double ta() override { return sigma; }
    void delta_ext(double e, List const &xb) override {
        nExt++;
        for (auto const &x : xb) if (x.pin == in) count++;
        if (!active) { active = true; sigma = 0.1; } else if (sigma < INF) sigma -= e;
    }
    void delta_int() override { nInt++; active = false; sigma = INF; }
    void delta_conf(List const &xb) override { delta_int(); delta_ext(0, xb); }
    void output_func(List &yb) override { yb.push_back(PinValue(out, count)); }
};

struct Sink : Atomic {
    pin_t in;
    double ta() override { return INF; }
    void delta_ext(double, List const &xb) override { nExt++; nSink += (long long)xb.size(); }
    void delta_int() override {}
    void delta_conf(List const &xb) override { delta_ext(0, xb); }
    void output_func(List &) override {}
};

struct Level : Coupled {
    pin_t in, out;
    Level(int w, int d) {
        int np = d > 1 ? w - 1 : w;
        for (int i = 0; i < np; i++) {
            auto p = std::make_shared<Proc>();
            add_atomic(p);
            create_coupling(in, p->in);
            create_coupling(p->in, p);
            if (i == 0) create_coupling(p->out, out);
        }
        if (d > 1) {
            auto sub = std::make_shared<Level>(w, d - 1);
            add_coupled_model(sub);
            create_coupling(in, sub->in);
            create_coupling(sub->out, out);
        }
    }
};

struct DevStoneTop : Coupled {
    DevStoneTop(int w, int d, int n) {
        auto gen = std::make_shared<Gen>(n);
        auto lv = std::make_shared<Level>(w, d);
        auto sink = std::make_shared<Sink>();
        add_atomic(gen); add_coupled_model(lv); add_atomic(sink);
        create_coupling(gen->out, lv->in);
        create_coupling(lv->out, sink->in);
        create_coupling(sink->in, sink);
    }
};

// --- RL-shaped --------------------------------------------------------------------
static long long lcg(long long x) { return (x * 1103515245LL + 12345LL) % 2147483648LL; }

struct Section : Atomic {
    pin_t act, obs; int idx; long long rng; int last = 0; double sigma = INF; int phase = 0;  // 0 travel 1 wait 2 dwell
    explicit Section(int idx) : idx(idx), rng(lcg(episodeSeed * 7919 + idx + 1)) { travel(); }
    void travel() { rng = lcg(rng); last = 1 + (int)((rng >> 16) % 5); phase = 0; sigma = last; }
    double ta() override { return sigma; }
    void delta_int() override { if (phase == 0) { phase = 1; sigma = INF; } else travel(); }
    void delta_ext(double e, List const &xb) override {
        for (auto const &x : xb) {
            if (x.value / 10 == idx && phase == 1) { phase = 2; sigma = x.value % 10; return; }
        }
        if (sigma < INF) sigma -= e;
    }
    void delta_conf(List const &xb) override { delta_int(); delta_ext(0, xb); }
    void output_func(List &yb) override { if (phase == 0) yb.push_back(PinValue(obs, idx * 1000 + last)); }
};

struct Agent : Atomic {
    pin_t obs, act; long long rng; std::vector<int> pending; double sigma = INF;
    Agent() : rng(lcg(episodeSeed + 424242)) {}
    double ta() override { return sigma; }
    void delta_ext(double, List const &xb) override {
        std::vector<int> o;
        for (auto const &x : xb) o.push_back(x.value);
        std::sort(o.begin(), o.end());
        for (int v : o) {
            int idx = v / 1000, travel = v % 1000;
            reward += 3 - std::abs(travel - 3);
            decisions++;
            rng = lcg(rng);
            pending.push_back(idx * 10 + (int)((travel + (rng >> 16) % 2) % 4));
        }
        sigma = 0.0;
    }
    void delta_int() override { pending.clear(); sigma = INF; }
    void delta_conf(List const &xb) override { delta_int(); delta_ext(0, xb); }
    void output_func(List &yb) override { for (int a : pending) yb.push_back(PinValue(act, a)); }
};

struct RLEnv : Coupled {
    explicit RLEnv(int m) {
        auto agent = std::make_shared<Agent>();
        add_atomic(agent);
        create_coupling(agent->obs, agent);
        for (int i = 0; i < m; i++) {
            auto s = std::make_shared<Section>(i);
            add_atomic(s);
            create_coupling(s->obs, agent->obs);
            create_coupling(agent->act, s->act);
            create_coupling(s->act, s);
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
            Simulator sim(top);
            while (sim.nextEventTime() < INF) sim.execNextEvent();
            double t2 = now_ms();
            b += (r ? "," : "") + std::to_string(t1 - t0);
            s += (r ? "," : "") + std::to_string(t2 - t1);
        }
        printf("{\"engine\": \"adevs\", \"w\": %d, \"d\": %d, \"n\": %d, \"int\": %lld, \"ext\": %lld, "
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
            Simulator sim(std::make_shared<RLEnv>(m));
            while (sim.nextEventTime() <= horizon) sim.execNextEvent();
            ep.push_back(now_ms() - s);
        }
        double t2 = now_ms(), first = ep[0];
        std::sort(ep.begin(), ep.end());
        printf("{\"engine\": \"adevs\", \"sections\": %d, \"episodes\": %d, \"horizon\": %.1f, "
               "\"decisions\": %lld, \"reward\": %lld, \"build_ms\": 0.0, \"run_ms\": %f, "
               "\"first_ep_ms\": %f, \"ep_ms_median\": %f}\n", m, episodes, horizon, decisions, reward,
               t2 - t1, first, ep[episodes / 2]);
    }
}
