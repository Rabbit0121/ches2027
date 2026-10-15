using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

public static partial class Engine
{
    // A cache entry is specific to BOTH limits. A faster, deeper expression
    // must never replace a shallower representative in another domain.
    public static int CacheLimit = 24;
    public static long LibraryTuples = 0;
    private static readonly Dictionary<Tuple<int,int>, Dictionary<ulong,Node>> LibraryCache
        = new Dictionary<Tuple<int,int>, Dictionary<ulong,Node>>();
    private static readonly Queue<Tuple<int,int>> LibraryOrder
        = new Queue<Tuple<int,int>>();

    public static void ClearLibraryCache()
    {
        LibraryCache.Clear();
        LibraryOrder.Clear();
    }

    private static void KeepLibrary(Dictionary<ulong,Node> map, Node value)
    {
        Node old;
        if (!map.TryGetValue(value.F, out old) || value.T < old.T)
            map[value.F] = value;
    }

    public static Dictionary<ulong,Node> Library(int bound, int depth)
    {
        Check();
        if (depth < 1 || bound < MinCost)
            return new Dictionary<ulong,Node>(TruthKeys);

        depth = Math.Min(depth, bound / MinCost);

        var key = Tuple.Create(bound, depth);
        Dictionary<ulong,Node> cached;
        if (LibraryCache.TryGetValue(key, out cached)) return cached;

        var result = new Dictionary<ulong,Node>(TruthKeys);
        for (int x = 0; x < Inputs.Length; ++x)
        {
            if (Cost[0] <= bound) KeepLibrary(result, MakeSeed(0, x));
            if (Cost[1] <= bound) KeepLibrary(result, MakeSeed(1, x));
        }

        if (depth > 1 && bound >= 2 * MinCost)
        {
            // Every non-boundary root has positive cost at least MinCost.
            // Its children therefore lie in this complete smaller domain.
            var smaller = Library(bound - MinCost, depth - 1);
            foreach (Node n in smaller.Values) KeepLibrary(result, n);

            // Stable ordering also makes equal-cost witness selection stable
            // across different worker counts.
            Node[] source = smaller.Values.OrderBy(n => n.T).ThenBy(n => n.F).ToArray();
            var maps = new Dictionary<ulong,Node>[Names.Length];
            var options = new ParallelOptions { MaxDegreeOfParallelism = Math.Max(1, ThreadCount) };

            // Seed representatives are already present. Internal BUF is strictly
            // dominated by its own child, hence cannot create a faster function.
            Interlocked.Increment(ref ParallelRegions);
            try { Parallel.For(0, Names.Length, options, g =>
            {
                if (g == 1 || !Enabled[g])
                {
                    maps[g] = new Dictionary<ulong,Node>(TruthKeys);
                    return;
                }
                int eligible = 0;
                int limit = bound - Cost[g];
                while (eligible < source.Length && source[eligible].T <= limit) ++eligible;
                maps[g] = EnumerateLibraryGate(g, source, eligible, result);
            }); } finally {Interlocked.Decrement(ref ParallelRegions);}

            // Do not merge concurrently: native dictionary reads are safe only
            // while no worker mutates the shared base dictionary.
            for (int g = 0; g < maps.Length; ++g)
                foreach (Node n in maps[g].Values) KeepLibrary(result, n);
        }

        if (CacheLimit > 0)
        {
            while (LibraryCache.Count >= CacheLimit && LibraryOrder.Count > 0)
                LibraryCache.Remove(LibraryOrder.Dequeue());
            LibraryCache[key] = result;
            LibraryOrder.Enqueue(key);
        }
        OnProgress("library bound=" + bound + " depth=" + depth + " functions=" + result.Count);
        return result;
    }

    private static Dictionary<ulong,Node> EnumerateLibraryGate(
        int g, Node[] source, int count, Dictionary<ulong,Node> known)
    {
        var output = new Dictionary<ulong,Node>(TruthKeys);
        long tuples = 0;

        // No temporary pin arrays, expression nodes, or LINQ calls per tuple.
        Action<int,int,int,int> offer = (ia, ib, ic, id) =>
        {
            if ((++tuples & 4095L) == 0) Check();
            Node a = source[ia];
            Node b = ib >= 0 ? source[ib] : null;
            Node c = ic >= 0 ? source[ic] : null;
            Node d = id >= 0 ? source[id] : null;
            int time = a.T;
            if (b != null && b.T > time) time = b.T;
            if (c != null && c.T > time) time = c.T;
            if (d != null && d.T > time) time = d.T;
            time += Cost[g];
            ulong truth = Eval(g, a.F, b == null ? 0UL : b.F,
                c == null ? 0UL : c.F, d == null ? 0UL : d.F);
            Node old;
            if (known.TryGetValue(truth, out old) && old.T <= time) return;
            if (output.TryGetValue(truth, out old) && old.T <= time) return;
            output[truth] = Make(g, a, b, c, d);
        };

        Check();
        try
        {
            int arity = Arity[g];
            if (arity == 1)
            {
                for (int a = 0; a < count; ++a) offer(a, -1, -1, -1);
            }
            else if (g == 14) // MUX2: all three pins have distinct roles.
            {
                for (int a = 0; a < count; ++a)
                    for (int b = 0; b < count; ++b)
                        for (int c = 0; c < count; ++c) offer(a, b, c, -1);
            }
            else if (g == 9 || g == 10) // OAI21 / AOI21
            {
                for (int a = 0; a < count; ++a)
                    for (int b = a; b < count; ++b)
                        for (int c = 0; c < count; ++c) offer(a, b, c, -1);
            }
            else if (g == 15 || g == 16) // OAI22 / AOI22
            {
                // Each pair is sorted, and the pair pair is lexicographically
                // sorted. Repeated pins and repeated pairs are both included.
                for (int a = 0; a < count; ++a)
                    for (int b = a; b < count; ++b)
                        for (int c = a; c < count; ++c)
                            for (int d = c == a ? b : c; d < count; ++d)
                                offer(a, b, c, d);
            }
            else if (arity == 2)
            {
                for (int a = 0; a < count; ++a)
                    for (int b = a; b < count; ++b) offer(a, b, -1, -1);
            }
            else if (arity == 3)
            {
                for (int a = 0; a < count; ++a)
                    for (int b = a; b < count; ++b)
                        for (int c = b; c < count; ++c) offer(a, b, c, -1);
            }
            else if (arity == 4)
            {
                for (int a = 0; a < count; ++a)
                    for (int b = a; b < count; ++b)
                        for (int c = b; c < count; ++c)
                            for (int d = c; d < count; ++d) offer(a, b, c, d);
            }
            else throw new InvalidOperationException("Unsupported gate arity");
        }
        finally { Interlocked.Add(ref LibraryTuples, tuples); }
        return output;
    }
}
