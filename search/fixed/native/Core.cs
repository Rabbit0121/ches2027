using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Text.Json;

public sealed class Node {
    public ulong F;
    public int T, H, G, X = -1;
    public Node[] A = Array.Empty<Node>();
}

public sealed class SearchConfig {
    public string Mode { get; set; } = "legacy";
    public int WholeDepth { get; set; } = 0;
    public int MaxStates { get; set; } = 100000;
    public int MaxDemands { get; set; } = 128;
    public bool AdaptiveFeedback { get; set; } = true;
    public bool AdaptiveCovers { get; set; } = true;
    public bool AdaptiveRefresh { get; set; } = false;
    public long DecisionLogMaxBytes { get; set; } = 50L * 1024 * 1024;
    public long RssBudgetBytes { get; set; } = 0;
    public long HeapSoftBytes { get; set; } = 0;
    public int MaxPendingResidualTasks { get; set; } = 32768;
    public double CoverDiscoveryShare { get; set; } = 0.5;
    public bool Exchange { get; set; } = false;
    public JsonElement Initial { get; set; }
    public string Output { get; set; } = "";
    public int MaxDepth { get; set; } = 2;
    public int InputBits { get; set; }
    public int OutputBits { get; set; }
    public Dictionary<string,int> Costs { get; set; }
    public double SliceSeconds { get; set; } = 3;
    public double Seconds { get; set; }
    public int Threads { get; set; } = 1;
    public int CacheEntries { get; set; } = 24;
    public bool StopAfterFirst { get; set; }
    public int[] SBox { get; set; } = Array.Empty<int>();
}

public sealed class StopException : Exception {
    public StopException(string message) : base(message) {}
}

public static partial class Engine {
    public static readonly string[] Names = {
        "INV","BUF","NAND2","NOR2","AND2","OR2","XOR2","XNOR2",
        "NAND3","OAI21","AOI21","NOR3","AND3","OR3","MUX2",
        "OAI22","AOI22","NAND4","NOR4","AND4","OR4"
    };
    public static readonly int[] Cost = {
        22048,33557,27886,40650,40171,56414,73019,57604,34767,32651,
        51619,61543,51869,85840,75175,54596,57255,44487,91313,65492,118592
    };
    public static readonly int[] Arity = {
        1,1,2,2,2,2,2,2,3,3,3,3,3,3,3,4,4,4,4,4,4
    };
    public static int MinCost;
    public static bool[] Enabled = new bool[21];
    static double SliceDeadline=double.PositiveInfinity;
    static int SliceStops=0;
    public static ulong[] Inputs;
    public static ulong[] Target;
    public static int ThreadCount = 1;
    static int OwnerThread = Environment.CurrentManagedThreadId;
    static int ParallelRegions;
    // Dictionary indexing only; no file digests or checksum validation.
    sealed class TruthComparer : IEqualityComparer<ulong> {
        public bool Equals(ulong a,ulong b)=>a==b;
        public int GetHashCode(ulong value) {
            unchecked {
                value^=value>>30;value*=0xbf58476d1ce4e5b9UL;
                value^=value>>27;value*=0x94d049bb133111ebUL;
                value^=value>>31;return (int)(value^(value>>32));
            }
        }
    }
    public static readonly IEqualityComparer<ulong> TruthKeys=new TruthComparer();
    static SearchConfig Config;
    static Stopwatch Watch;
    static string Output, Status = "RUNNING", Reason;
    static int Current, Completed;
    static Node[] Best;
    static long LastStopPoll;
    static volatile bool StopRequested;
    // Incumbents are immutable nodes. A periodic heartbeat must not rewrite
    // their full circuit when only elapsed time has changed.
    static long BestVersion, SavedBestVersion = -1;
    static double LastProgressSave = double.NegativeInfinity;
    static long JsonWrites, IncumbentWrites, ProgressWrites;

    public static ulong Eval(int g, ulong a, ulong b=0, ulong c=0, ulong d=0) {
        return g switch {
            0=>~a, 1=>a, 2=>~(a&b), 3=>~(a|b), 4=>a&b, 5=>a|b,
            6=>a^b, 7=>~(a^b), 8=>~(a&b&c), 9=>~((a|b)&c),
            10=>~((a&b)|c), 11=>~(a|b|c), 12=>a&b&c, 13=>a|b|c,
            14=>(a&~c)|(b&c), 15=>~((a|b)&(c|d)),
            16=>~((a&b)|(c&d)), 17=>~(a&b&c&d), 18=>~(a|b|c|d),
            19=>a&b&c&d, 20=>a|b|c|d, _=>throw new ArgumentException("gate")
        };
    }

    public static Node MakeSeed(int g,int x) {
        return new Node { F=g==1?Inputs[x]:~Inputs[x],T=Cost[g],H=1,G=g,X=x };
    }

    public static Node Make(int g,Node a,Node b=null,Node c=null,Node d=null) {
        var children = Arity[g] switch {
            1=>new[]{a}, 2=>new[]{a,b}, 3=>new[]{a,b,c}, _=>new[]{a,b,c,d}
        };
        int t=0,h=0;
        foreach(var n in children) { t=Math.Max(t,n.T);h=Math.Max(h,n.H); }
        return new Node {F=Eval(g,a.F,b?.F??0,c?.F??0,d?.F??0),
                         T=t+Cost[g],H=h+1,G=g,A=children};
    }

    // Called periodically by native loops; no per-tuple file I/O.
    public static void Check() {
        if (Watch.Elapsed.TotalSeconds >= SliceDeadline) throw new SliceException();
        if (StopRequested) throw new StopException("stop requested");
        if (Config.Seconds>0 && Watch.Elapsed.TotalSeconds>=Config.Seconds)
            throw new StopException("time limit");
        long now=Environment.TickCount64;
        long old=Interlocked.Read(ref LastStopPoll);
        if (now-old>=250 && Interlocked.CompareExchange(ref LastStopPoll,now,old)==old) {
            if (File.Exists(Path.Combine(Output,"STOP"))) {
                StopRequested=true;
                throw new StopException("stop file requested");
            }
            if(Config.Mode=="adaptive" && MemoryPressure()) {
                // Parallel readers must finish before caches/queues are mutated.
                // The scheduler retries the slice and collects on its own thread.
                if(Environment.CurrentManagedThreadId!=OwnerThread || Volatile.Read(ref ParallelRegions)>0)
                    throw new SliceException();
                RecoverMemory();
                if(MemoryPressure())throw new StopException("native memory budget reached; unfinished queries are UNKNOWN");
            }
        }
    }

    public static void OnProgress(string message) {
        Console.WriteLine($"[{Watch.Elapsed.TotalSeconds:F1}s] {message}");
    }

    static void WriteJson(string name,object value) {
        string path=Path.Combine(Output,name),temp=path+".tmp";
        File.WriteAllText(temp,JsonSerializer.Serialize(value,
            new JsonSerializerOptions {WriteIndented=true}));
        for(int attempt=0;;attempt++) {
            try {File.Move(temp,path,true);break;}
            catch(IOException) when(attempt<20) {Thread.Sleep(Math.Min(200,10*(attempt+1)));}
            catch(UnauthorizedAccessException) when(attempt<20) {Thread.Sleep(Math.Min(200,10*(attempt+1)));}
        }
        JsonWrites++;
    }

    static object Circuit() {
        var names=new Dictionary<Node,string>();
        var rows=new List<object>();
        string Visit(Node n) {
            if(names.TryGetValue(n,out var existing)) return existing;
            var ins=n.X>=0?new[]{"x"+n.X}:n.A.Select(Visit).ToArray();
            string name="n"+rows.Count;
            names[n]=name;
            rows.Add(new Dictionary<string,object>{["id"]=name,["out"]=name,
                ["type"]=Names[n.G],["in"]=ins,["arrival_fs"]=n.T,["depth"]=n.H});
            return name;
        }
        var outputs=new Dictionary<string,string>();
        var times=new Dictionary<string,int>();
        var depths=new Dictionary<string,int>();
        for(int j=0;j<Target.Length;j++) if(Best[j]!=null) {
            outputs["y"+j]=Visit(Best[j]);times["y"+j]=Best[j].T;depths["y"+j]=Best[j].H;
        }
        var path=new List<object>();int worst=-1;
        for(int j=0;j<Target.Length;j++) if(Best[j]!=null && (worst<0||Best[j].T>Best[worst].T)) worst=j;
        if(worst>=0) {
            Node n=Best[worst];
            while(true) {
                path.Add(new {node=names[n],gate=Names[n.G],increment_fs=Cost[n.G],arrival_fs=n.T});
                if(n.X>=0) {path.Add(new{node="x"+n.X,arrival_fs=0});break;}
                n=n.A.OrderByDescending(a=>a.T).First();
            }
            path.Reverse();
        }
        return new {gates=rows,gate_count=rows.Count,outputs,outputs_fs=times,
            outputs_depth=depths,all_outputs_found=outputs.Count==Target.Length,
            worst_found_fs=worst<0?(int?)null:Best[worst].T,
            critical_output=worst<0?null:"y"+worst,critical_path=path};
    }

    static void Save(bool force=false) {
        FlushTrace();
        bool changed=SavedBestVersion!=BestVersion;
        if(changed) {
            WriteJson("best.json",Circuit());
            SavedBestVersion=BestVersion;IncumbentWrites++;
        }
        double now=Watch.Elapsed.TotalSeconds;
        if(!force && !changed && Status=="RUNNING" && now-LastProgressSave<2)return;
        var times=new Dictionary<string,int>();
        for(int j=0;j<Target.Length;j++) if(Best[j]!=null) times["y"+j]=Best[j].T;
        WriteJson("progress.json",new {status=Status,reason=Reason,
            elapsed_seconds=Watch.Elapsed.TotalSeconds,engine=Config.Mode,
            base_depth=Config.Mode=="adaptive"?(int?)null:Config.MaxDepth,
            max_depth=Config.Mode=="adaptive" && Config.WholeDepth>0?(int?)Config.WholeDepth:null,
            current_base_budget_fs=Current,last_finished_base_budget_fs=Completed,
            best_outputs_fs=times,all_outputs_found=times.Count==Target.Length,
            optimal_within_depth=Status=="OPTIMAL_WITHIN_DEPTH",
            global_optimality_proved=false,threads=ThreadCount,slice_timeouts=SliceStops,library_tuples=LibraryTuples,
            scheduler=Config.Mode=="adaptive"?AdaptiveProgress():null});
        LastProgressSave=now;ProgressWrites++;
    }

    static void Improve(int j,Node node,string source) {
        if(node!=null && node.F!=Target[j]) throw new InvalidOperationException("Invalid target witness");
        if(node==null || (Best[j]!=null && Best[j].T<=node.T)) return;
        // Metadata is supplied by construction, not by a separate validation run.
        Best[j]=node;BestVersion++;
        if(Config.Mode=="adaptive" && Trace!=null)Record(new{event_type="improvement",output=j,arrival_fs=node.T,depth=node.H,
            source,seconds=Watch.Elapsed.TotalSeconds,worst_fs=Best.All(n=>n!=null)?Best.Max(n=>n.T):(int?)null});
        FlushTrace(true);
        OnProgress($"improved y{j}: {node.T} fs; depth={node.H}; {source}");
        Save();
        if(Config.StopAfterFirst && Best.All(n=>n!=null))
            throw new StopException("first complete candidate requested");
    }

    static readonly int[][] Families = {
        new[]{2,8,17}, new[]{4,12,19}, new[]{3,11,18}, new[]{5,13,20}
    };
    static void AddBase(Dictionary<ulong,Node> source,ulong wanted,bool complement,
                        Dictionary<ulong,Node> pool) {
        int ticks=0;
        foreach(var n in source.Values) {
            if((++ticks&4095)==0) Check();
            ulong cover=complement?~n.F:n.F;
            if(cover==0 || (cover&~wanted)!=0) continue;
            if(!pool.TryGetValue(cover,out var old)||n.T<old.T) pool[cover]=n;
        }
    }
    static void TryFamily(int j,int family,ulong wanted,Dictionary<ulong,Node> pool) {
        foreach(int root in Families[family]) {
            if(!Enabled[root]) continue;
            Check();int limit=Best[j]==null?int.MaxValue:Best[j].T-Cost[root]-1;
            if(limit<MinCost) continue;
            Improve(j,FindCover(pool,wanted,root,limit),Names[root]);
        }
    }

    sealed class SliceException : Exception {}

    static void Slice(Action action) {
        SliceDeadline=Watch.Elapsed.TotalSeconds+Config.SliceSeconds;
        try {action();}
        catch(SliceException) {SliceStops++;}
        finally {SliceDeadline=double.PositiveInfinity;}
    }

    public static int Run(string configPath) {
        Config=JsonSerializer.Deserialize<SearchConfig>(File.ReadAllText(configPath));
        if(Config==null || Config.InputBits<1 || Config.InputBits>6 || Config.OutputBits<1 || Config.OutputBits>16 ||
           Config.SBox.Length!=(1<<Config.InputBits) || Config.SBox.Any(v=>v<0||v>=(1<<Config.OutputBits)) ||
           Config.MaxDepth<1 || (Config.Mode!="adaptive" && Config.MaxDepth>4) || Config.SliceSeconds<=0 || Config.Seconds<0 || Config.DecisionLogMaxBytes<0 || Config.RssBudgetBytes<0 || Config.HeapSoftBytes<0 ||
           Config.MaxPendingResidualTasks<0 || !double.IsFinite(Config.CoverDiscoveryShare) || Config.CoverDiscoveryShare<0 || Config.CoverDiscoveryShare>1)
            throw new ArgumentException("Invalid configuration");
        for(int g=0;g<Names.Length;g++) {
            Enabled[g]=Config.Costs.TryGetValue(Names[g],out int c);
            if(Enabled[g]) {if(c<=0)throw new ArgumentException("Nonpositive cost");Cost[g]=c;}
        }
        if(!Enabled[0]||!Enabled[1])throw new ArgumentException("Paid INV/BUF required");
        MinCost=Enumerable.Range(0,21).Where(g=>Enabled[g]).Min(g=>Cost[g]);
        Inputs=new ulong[Config.InputBits];Target=new ulong[Config.OutputBits];Best=new Node[Target.Length];
        // Repeat small truth tables to fill ulong. Complement and all gates commute
        // with this embedding, so the 64-bit accelerated kernels need no masks.
        for(int x=0;x<64;x++) {
            for(int i=0;i<Inputs.Length;i++) if(((x>>i)&1)!=0)Inputs[i]|=1UL<<x;
            for(int j=0;j<Target.Length;j++)if(((Config.SBox[x%Config.SBox.Length]>>j)&1)!=0)Target[j]|=1UL<<x;
        }
        OwnerThread=Environment.CurrentManagedThreadId;
        Output=Config.Output;ThreadCount=Config.Threads;CacheLimit=Config.CacheEntries;
        BestVersion=0;SavedBestVersion=-1;LastProgressSave=double.NegativeInfinity;
        JsonWrites=IncumbentWrites=ProgressWrites=0;
        Watch=Stopwatch.StartNew();Save();
        if(Config.Mode=="adaptive")return RunAdaptive();
        try {
            // First build the entire depth-limited base domain. Its deadline is
            // derived solely from the gate table, never a known solution delay.
            int ceiling=Math.Max(Cost[0],Cost[1])+(Config.MaxDepth-1)*Enumerable.Range(0,21).Where(g=>Enabled[g]).Max(g=>Cost[g]);
            var basis=Library(ceiling,Config.MaxDepth);
            foreach(int j in Enumerable.Range(0,Target.Length))
                if(basis.TryGetValue(Target[j],out var node))Improve(j,node,"base domain");
            var levels=basis.Values.Select(n=>n.T).Distinct().OrderBy(t=>t).ToArray();
            var pools=new Dictionary<ulong,Node>[Target.Length,4];
            for(int j=0;j<Target.Length;j++)for(int f=0;f<4;f++)pools[j,f]=new Dictionary<ulong,Node>(TruthKeys);
            // Tasks ordered by prospective delay; every enabled middle gate and
            // every cover family is considered. Slice interruption is only UNKNOWN.
            var jobs=new List<(int budget,int g,int family,int estimate)>();
            foreach(int b in levels)for(int f=0;f<4;f++) {
                var roots=Families[f].Where(r=>Enabled[r]).ToArray();
                if(roots.Length==0)continue;
                int rootCost=roots.Min(r=>Cost[r]);
                jobs.Add((b,-1,f,b+rootCost));
                for(int g=0;g<21;g++)if(Enabled[g] && g!=1)jobs.Add((b,g,f,b+Cost[g]+rootCost));
            }
            foreach(var job in jobs.OrderBy(v=>v.estimate).ThenBy(v=>v.g).ThenBy(v=>v.family)) {
                Check();Current=job.budget;
                if(Best.All(n=>n!=null && n.T<=job.estimate))continue;
                var eligible=basis.Where(v=>v.Value.T<=job.budget).ToDictionary(v=>v.Key,v=>v.Value,TruthKeys);
                for(int j=0;j<Target.Length;j++) {
                    if(Best[j]!=null && Best[j].T<=job.estimate)continue;
                    bool complement=job.family<2;
                    ulong wanted=(job.family==0||job.family==3)?Target[j]:~Target[j];
                    var pool=pools[j,job.family];
                    Slice(()=> {
                        if(job.g<0)AddBase(eligible,wanted,complement,pool);
                        else AddMiddle(eligible,wanted,complement,job.g,pool);
                        TryFamily(j,job.family,wanted,pool);
                    });
                }
                Completed=Current;Save();
            }
            Status=Best.All(n=>n!=null)?"FEASIBLE":"INCOMPLETE";
            Reason="Finite discovery portfolio exhausted; no global lower-bound claim";
        } catch(StopException e) {
            Status=Best.Any(n=>n!=null)?"STOPPED_WITH_INCUMBENT":"INCOMPLETE";Reason=e.Message;
        } catch(AggregateException e) {
            var errors=e.Flatten().InnerExceptions;
            Status=errors.All(x=>x is StopException)?"INCOMPLETE":"ERROR";Reason=e.GetType().Name;
        } catch(Exception e) {Status="ERROR";Reason=e.GetType().Name;}
        finally {SliceDeadline=double.PositiveInfinity;Save();}
        OnProgress(Status);return Status=="ERROR"?1:Best.All(n=>n!=null)?0:2;
    }
}
