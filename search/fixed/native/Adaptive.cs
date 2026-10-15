using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using System.Text;

public static partial class Engine {
    // All queues are generated from the current problem, never from an S-box id.
    sealed class Work {
        public int Id, Age, Attempts, Estimate, Services, Ticket, Output=-1;
        public string Kind, Detail;
        public Func<bool> Step;
    }
    sealed class Frontier {
        public int Id,H;
        public Node[] Nodes;
        public Dictionary<ulong,Node> Map;
        public MatchIndex Index;
        public ulong[] Prefix;
        public Dictionary<(int,int),Node[]> CandidateViews=new Dictionary<(int,int),Node[]>();
    }
    sealed class MatchIndex {
        public Node[] Nodes;
        public ulong[][] Ones;
        public MatchIndex(Node[] nodes) {
            Nodes=nodes;int words=(nodes.Length+63)/64;
            Ones=Enumerable.Range(0,64).Select(_=>new ulong[words]).ToArray();
            for(int i=0;i<nodes.Length;i++) {
                ulong bits=nodes[i].F;
                while(bits!=0) {ulong bit=bits&(~bits+1);bits^=bit;Ones[CovBit(bit)][i>>6]|=1UL<<(i&63);}
            }
        }
        public Node Find(ulong value,ulong care,int bound,int depth) {
            for(int w=0;w<(Nodes.Length+63)/64;w++) {
                if(Nodes[w*64].T>bound)break;
                ulong ids=~0UL;int remaining=Nodes.Length-w*64;
                if(remaining<64)ids=(1UL<<remaining)-1;
                ulong bits=care;
                while(bits!=0 && ids!=0) {
                    ulong bit=bits&(~bits+1);bits^=bit;
                    ids&=(value&bit)!=0?Ones[CovBit(bit)][w]:~Ones[CovBit(bit)][w];
                }
                while(ids!=0) {
                    ulong bit=ids&(~ids+1);ids^=bit;
                    Node n=Nodes[w*64+CovBit(bit)];
                    if(n.T<=bound && n.H<=depth)return n;
                }
            }
            return null;
        }
    }
    sealed class Need {
        public ulong Value,Care;
        public int Bound,H,Output=-1;
        public List<Action<Node>> Users=new List<Action<Node>>();
        public Node Answer;
    }
    static readonly Dictionary<int,Dictionary<ulong,Node>> Archive=new Dictionary<int,Dictionary<ulong,Node>>();
    static readonly List<Frontier> Frontiers=new List<Frontier>();
    static readonly Dictionary<int,int> LevelRevisions=new Dictionary<int,int>();
    static readonly Dictionary<int,int> PublishedRevisions=new Dictionary<int,int>();
    static int FrontierRefreshes;
    static readonly Dictionary<int,Work> Agenda=new Dictionary<int,Work>();
    static readonly Dictionary<(string,int),PriorityQueue<(Work,int),double>> Queues=new Dictionary<(string,int),PriorityQueue<(Work,int),double>>();
    static readonly Queue<(Work,int)> Waiting=new Queue<(Work,int)>();
    static readonly Queue<(Work,int)> DiscoveryWaiting=new Queue<(Work,int)>();
    static readonly Dictionary<string,int> PendingKinds=new Dictionary<string,int>();
    static readonly Dictionary<string,Need> Needs=new Dictionary<string,Need>();
    static readonly Dictionary<string,double> YieldRate=new Dictionary<string,double>();
    static readonly Dictionary<string,int> Runs=new Dictionary<string,int>();
    static readonly Dictionary<string,double> OperatorSeconds=new Dictionary<string,double>();
    sealed class Covers {
        public Dictionary<ulong,Node> Pool=new Dictionary<ulong,Node>(TruthKeys);
        public HashSet<(int,long,int,int)> NegativeQueries=new HashSet<(int,long,int,int)>();
        public HashSet<(int,int)> Pending=new HashSet<(int,int)>();
    }
    static readonly Dictionary<(int,int),Covers> CoverArchive=new Dictionary<(int,int),Covers>();
    static readonly Dictionary<(ulong,int),List<(Frontier,int,int)>> Interned=new Dictionary<(ulong,int),List<(Frontier,int,int)>>();
    static readonly HashSet<(int,int,int,int)> Generated=new HashSet<(int,int,int,int)>();
    static int InternId,GenerationHits,CoverHits;
    static int WorkId,Turn,Stored,Added,ArchiveDrops,NeedDrops,ImageChunks,RootChecks;
    static long QueueEntries,QueueCompactions,CoverMemoResets,MemoryRetries,MemoryCollections;
    static long RequestMemoryDeferrals;
    static long RequestQueueDeferrals;
    static int PeakResidualTasks;
    static StreamWriter Trace;
    static long TraceBytes,TraceRecords,TraceSkipped;
    static bool TraceLimitReached;
    static double LastTraceFlush;
    static long TraceFlushes;
    static double WorkSeconds,FairSeconds,DiscoverySeconds,NeedProgress;
    static int WholeLimit => Config.WholeDepth>0?Config.WholeDepth:int.MaxValue;
    static bool IsDiscovery(string kind) => kind=="cover" || kind=="demand";
    static int Pending(string kind) => PendingKinds.TryGetValue(kind,out int count)?count:0;
    static object AdaptiveProgress() => new {
        archive_states=Stored,requests=Needs.Count,pending_tasks=Agenda.Count,
        pending_by_kind=PendingKinds.ToDictionary(v=>v.Key,v=>v.Value),
        peak_residual_tasks=PeakResidualTasks,max_pending_residual_tasks=Config.MaxPendingResidualTasks,
        request_queue_deferrals=RequestQueueDeferrals,request_memory_deferrals=RequestMemoryDeferrals,
        operator_runs=Runs.ToDictionary(v=>v.Key,v=>v.Value),
        operator_seconds=OperatorSeconds.ToDictionary(v=>v.Key,v=>v.Value),
        work_seconds=WorkSeconds,cover_discovery_seconds=DiscoverySeconds,
        cover_discovery_share=Config.CoverDiscoveryShare,
        heap_bytes=GC.GetTotalMemory(false),rss_bytes=Environment.WorkingSet
    };

    static bool ArchiveNode(Node n) {
        if(n.H>WholeLimit)return false;
        // A slower AND deeper implementation is not new useful information.
        // Keep the real arrival/depth Pareto frontier, including slower shallow
        // witnesses that a tighter depth constraint can still need.
        foreach(var item in Archive)if(item.Key<=n.H && item.Value.TryGetValue(n.F,out var better) && better.T<=n.T)return false;
        foreach(var item in Archive)if(item.Key>=n.H && item.Value.TryGetValue(n.F,out var worse) && worse.T>=n.T) {
            item.Value.Remove(n.F);Stored--;
        }
        if(!Archive.TryGetValue(n.H,out var level))Archive[n.H]=level=new Dictionary<ulong,Node>(TruthKeys);
        if(level.TryGetValue(n.F,out var old) && old.T<=n.T)return false;
        if(old==null && Stored>=Config.MaxStates) {ArchiveDrops++;return false;}
        if(old==null)Stored++;
        level[n.F]=n;Added++;
        LevelRevisions[n.H]=(LevelRevisions.TryGetValue(n.H,out int revision)?revision:0)+1;
        // Independent of target identity: any generated function can help any output.
        for(int j=0;j<Target.Length;j++)if(n.F==Target[j])Improve(j,n,"adaptive archive");
        return true;
    }
    static void Schedule(Work work) {
        if(!Agenda.ContainsKey(work.Id)) {
            PendingKinds[work.Kind]=Pending(work.Kind)+1;
            if(work.Kind=="residual")PeakResidualTasks=Math.Max(PeakResidualTasks,Pending("residual"));
        }
        work.Ticket++;work.Age=Turn;Agenda[work.Id]=work;
        var key=(work.Kind,work.Output);
        if(!Queues.TryGetValue(key,out var queue))Queues[key]=queue=new PriorityQueue<(Work,int),double>();
        queue.Enqueue((work,work.Ticket),(double)work.Estimate/MinCost+(work.Attempts>0?0.25:1)*Math.Log2(1+work.Services));
        QueueEntries++;Waiting.Enqueue((work,work.Ticket));
        if(IsDiscovery(work.Kind))DiscoveryWaiting.Enqueue((work,work.Ticket));
        long allowance=Math.Max(4096,2L*Agenda.Count);
        if(QueueEntries>allowance || Waiting.Count>allowance || DiscoveryWaiting.Count>allowance)CompactQueues();
        if((Agenda.Count&8191)==0)Check();
    }
    static void CompactQueues() {
        // Only invalid tickets are removed. Live priorities and FIFO ages stay
        // unchanged, so memory cleanup cannot starve an existing work item.
        QueueEntries=0;
        foreach(var key in Queues.Keys.ToArray()) {
            var fresh=new PriorityQueue<(Work,int),double>();
            foreach(var item in Queues[key].UnorderedItems)
                if(Active(item.Element))fresh.Enqueue(item.Element,item.Priority);
            Queues[key]=fresh;QueueEntries+=fresh.Count;
        }
        int count=Waiting.Count;
        for(int i=0;i<count;i++) {var item=Waiting.Dequeue();if(Active(item))Waiting.Enqueue(item);}
        Waiting.TrimExcess();QueueCompactions++;
        count=DiscoveryWaiting.Count;
        for(int i=0;i<count;i++) {var item=DiscoveryWaiting.Dequeue();if(Active(item))DiscoveryWaiting.Enqueue(item);}
        DiscoveryWaiting.TrimExcess();
    }
    static bool MemoryPressure() =>
        (Config.HeapSoftBytes>0 && GC.GetTotalMemory(false)>Config.HeapSoftBytes) ||
        (Config.RssBudgetBytes>0 && Environment.WorkingSet>Config.RssBudgetBytes);
    static bool RequestGrowthPressure() => Config.HeapSoftBytes>0 &&
        GC.GetTotalMemory(false)>Config.HeapSoftBytes-Config.HeapSoftBytes/10;
    static void RecoverMemory() {
        ClearLibraryCache();GC.Collect();CompactQueues();GC.Collect();MemoryCollections++;
    }
    static bool ExecuteWork(Work job) {
        try {return job.Step();}
        catch(OutOfMemoryException) {
            MemoryRetries++;RecoverMemory();throw new SliceException();
        }
        catch(AggregateException e) when(e.Flatten().InnerExceptions.All(x=>x is SliceException || x is OutOfMemoryException)
            && e.Flatten().InnerExceptions.Any(x=>x is OutOfMemoryException)) {
            MemoryRetries++;RecoverMemory();throw new SliceException();
        }
        catch(AggregateException e) when(e.Flatten().InnerExceptions.All(x=>x is SliceException || x is StopException || x is OutOfMemoryException)
            && e.Flatten().InnerExceptions.Any(x=>x is StopException)) {
            throw e.Flatten().InnerExceptions.OfType<StopException>().First();
        }
    }
    static void Enqueue(string kind,string detail,int estimate,Func<bool> step,int output=-1) {
        Schedule(new Work{Id=WorkId++,Kind=kind,Detail=detail,Estimate=estimate,Step=step,Output=output});
    }
    static bool Active((Work,int) entry) => Agenda.ContainsKey(entry.Item1.Id) && entry.Item1.Ticket==entry.Item2;
    static Work NextWork(out bool fair,out bool discovery) {
        // Reserve service time for constructive generation and cover queries.
        // The reservation is work-conserving when that class has no live jobs.
        discovery=Pending("cover")+Pending("demand")>0 && DiscoverySeconds<WorkSeconds*Config.CoverDiscoveryShare;
        fair=FairSeconds<=WorkSeconds/8;
        return Pick(fair,discovery);
    }
    static Work Pick(bool fair,bool discovery=false) {
        Work selected=null;
        if(fair) {
            var waiting=discovery?DiscoveryWaiting:Waiting;
            while(waiting.Count>0&&!Active(waiting.Peek()))waiting.Dequeue();
            if(waiting.Count>0)selected=waiting.Dequeue().Item1;
        } else {
            double bestScore=double.PositiveInfinity;
            int worst=Best.Where(n=>n!=null).Select(n=>n.T).DefaultIfEmpty(1).Max();
            foreach(var queue in Queues.Values) {
                while(queue.Count>0&&!Active(queue.Peek())) {queue.Dequeue();QueueEntries--;}
                if(!queue.TryPeek(out var entry,out double priority))continue;
                Work w=entry.Item1;
                if(discovery&&!IsDiscovery(w.Kind))continue;
                double rate=Config.AdaptiveFeedback && YieldRate.TryGetValue(w.Kind,out var r)?r:0;
                double urgency=w.Output<0?1:(Best[w.Output]==null?1.5:1+0.5*Best[w.Output].T/Math.Max(1.0,worst));
                double average=Runs.TryGetValue(w.Kind,out int calls)?OperatorSeconds[w.Kind]/calls:0;
                double workCost=1+Math.Log2(1+average/Config.SliceSeconds);
                double score=priority*workCost/(1+Math.Min(2,rate))/urgency;
                if(selected==null||score<bestScore || (score==bestScore && w.Age<selected.Age)) {selected=w;bestScore=score;}
            }
        }
        Agenda.Remove(selected.Id);PendingKinds[selected.Kind]=Pending(selected.Kind)-1;return selected;
    }
    static int BestCostSum() => Best.Sum(n=>n==null?0:(long)n.T)>int.MaxValue?int.MaxValue:Best.Where(n=>n!=null).Sum(n=>n.T);
    static void Record(object row) {
        if(Config.DecisionLogMaxBytes==0 || TraceLimitReached) {TraceSkipped++;return;}
        string line=JsonSerializer.Serialize(row);
        long bytes=Encoding.UTF8.GetByteCount(line)+Encoding.UTF8.GetByteCount(Trace.NewLine);
        // Keep complete JSONL records; the limit includes UTF-8 newline bytes.
        if(bytes>Config.DecisionLogMaxBytes-TraceBytes) {
            TraceLimitReached=true;TraceSkipped++;
            Console.WriteLine("Decision log limit reached; detailed logging stopped, search continues.");
            FlushTrace(true);
            return;
        }
        Trace.WriteLine(line);
        TraceBytes+=bytes;TraceRecords++;
        FlushTrace();
    }

    static void FlushTrace(bool force=false) {
        if(Trace==null)return;
        double now=Watch?.Elapsed.TotalSeconds??0;
        if(!force && now-LastTraceFlush<1)return;
        Trace.Flush();LastTraceFlush=now;TraceFlushes++;
    }

    // Ordered tuples for a gate relation, with genuine pin symmetries only.
    static IEnumerable<int[]> Tuples(int g,int count,int length) {
        int[] row=new int[length];
        IEnumerable<int[]> Walk(int pin) {
            if(pin==length) {yield return (int[])row.Clone();yield break;}
            int start=0;
            if(g!=14) {
                if(g==9||g==10) {if(pin==1)start=row[0];}
                else if(g==15||g==16) {
                    if(pin==1)start=row[0];
                    if(pin==2)start=row[0];
                    if(pin==3)start=row[2]==row[0]?Math.Max(row[1],row[2]):row[2];
                } else if(pin>0)start=row[pin-1];
            }
            for(int i=start;i<count;i++) {row[pin]=i;foreach(var ids in Walk(pin+1))yield return ids;}
        }
        return Walk(0);
    }
    static Node Compose(int g,Node[] args) => Make(g,args[0],args.Length>1?args[1]:null,args.Length>2?args[2]:null,args.Length>3?args[3]:null);
    static int DomainToken(Frontier source,int count) {
        var key=(source.Prefix[count],count);
        if(!Interned.TryGetValue(key,out var bucket))Interned[key]=bucket=new List<(Frontier,int,int)>();
        foreach(var entry in bucket) {
            bool equal=true;
            for(int i=0;i<count;i++) {
                Node a=source.Nodes[i],b=entry.Item1.Nodes[i];
                if(a.F!=b.F||a.T!=b.T||a.H!=b.H) {equal=false;break;}
            }
            if(equal)return entry.Item3;
        }
        int id=InternId++;bucket.Add((source,count,id));return id;
    }
    public static ulong[] InvertLastPin(int g,ulong[] prefix,ulong value,ulong care) {
        if(g<0||g>=Arity.Length||prefix.Length!=Arity[g]-1)throw new ArgumentException("Invalid pin relation");
        ulong[] a=new ulong[4];Array.Copy(prefix,a,prefix.Length);
        ulong zero=Eval(g,a[0],a[1],a[2],a[3]);a[prefix.Length]=~0UL;
        ulong one=Eval(g,a[0],a[1],a[2],a[3]);
        ulong zeroOK=~(zero^value),oneOK=~(one^value);
        return new[]{care&~zeroOK,care&(zeroOK^oneOK),care&~(zeroOK|oneOK)};
    }

    static void Resolve(Need need,Node answer) {
        if(((answer.F^need.Value)&need.Care)!=0 || answer.T>need.Bound || answer.H>need.H)
            throw new InvalidOperationException("Invalid partial-care witness");
        if(need.Answer!=null && need.Answer.T<=answer.T)return;
        NeedProgress+=Math.Max(1,CovPop(need.Care))/64.0;
        need.Answer=answer;ArchiveNode(answer);
        foreach(var user in need.Users.ToArray())user(answer);
    }
    static void Request(Frontier source,ulong value,ulong care,int bound,int depth,Action<Node> user,int output=-1) {
        depth=Math.Min(depth,bound/MinCost);
        if(depth<1)return;
        var available=source.Index.Find(value,care,bound,depth);
        if(available!=null) {user(available);return;}
        // Resource cap only; a discarded request is NOT an infeasibility result.
        string key=source.Id+":"+value.ToString("X")+":"+care.ToString("X")+":"+bound+":"+depth;
        if(Needs.TryGetValue(key,out var known)) {
            if(RequestGrowthPressure()) {NeedDrops++;RequestMemoryDeferrals++;}
            else if(known.Users.Count<64)known.Users.Add(user);else NeedDrops++;
            if(known.Answer!=null)user(known.Answer);
            return;
        }
        // Recursively generated requests can outgrow the tasks being served.
        // Reserve query scratch space and keep consuming existing work instead
        // of exhausting the heap with new closures. This is UNKNOWN discovery
        // work, never a negative feasibility result.
        if(RequestGrowthPressure()) {
            NeedDrops++;RequestMemoryDeferrals++;return;
        }
        // RAM is archive capacity, not a license to grow an unbounded residual
        // agenda. Reserve space for all enabled root jobs before admitting a
        // new recursive request. A deferred request remains UNKNOWN and can
        // be requested again after existing jobs drain; no negative is cached.
        int rootJobs=Enumerable.Range(0,21).Count(g=>Enabled[g] && g!=1 && depth>1 && bound>=Cost[g]+MinCost);
        if(Config.MaxPendingResidualTasks>0 && Pending("residual")+(long)rootJobs>=Config.MaxPendingResidualTasks) {
            NeedDrops++;RequestQueueDeferrals++;return;
        }
        if(Needs.Count>=Config.MaxDemands) {NeedDrops++;return;}
        var need=new Need{Value=value&care,Care=care,Bound=bound,H=depth,Output=output};need.Users.Add(user);Needs[key]=need;
        for(int g=0;g<21;g++)if(Enabled[g] && g!=1 && depth>1 && bound>=Cost[g]+MinCost)
            QueryJob(source,need,g,"residual");
    }
    static void QueryJob(Frontier source,Need need,int g,string kind) {
        int childBound=need.Bound-Cost[g],childDepth=need.H-1;
        if(childBound<MinCost || childDepth<1)return;
        var candidates=CandidateView(source,childBound,childDepth);
        if(candidates.Length==0)return;
        // Last pin is matched by truth-table inversion; prefixes keep all roles.
        // Symmetry of complete pin tuples cannot restrict the absent last pin.
        var tuples=Tuples(g,candidates.Length,Arity[g]-1).GetEnumerator();
        int attempts=0;
        Enqueue(kind,$"frontier={source.Id} root={Names[g]} care={CovPop(need.Care)}",candidates[0].T+Cost[g],()=> {
            for(int q=0;q<32;q++) {
                if(!tuples.MoveNext())return true;
                var prefix=tuples.Current.Select(i=>candidates[i]).ToArray();
                var relation=InvertLastPin(g,prefix.Select(n=>n.F).ToArray(),need.Value,need.Care);
                if(relation[2]!=0)continue;
                ulong want=relation[0],care=relation[1];
                Node match=source.Index.Find(want,care,childBound,childDepth);RootChecks++;
                Action<Node> accept=n=>Resolve(need,Compose(g,prefix.Concat(new[]{n}).ToArray()));
                if(match!=null) {accept(match);return true;}
                // Missing signatures become explicit child problems, not a
                // special NAND-only expansion. Source and context remain paid.
                if(childDepth>1 && attempts++<4)Request(source,want,care,childBound,childDepth,accept,need.Output);
            }
            return false;
        },need.Output);
    }
    static Node[] CandidateView(Frontier source,int bound,int depth) {
        // A frontier is immutable. Identical query constraints must share the
        // exact same eligible array instead of retaining one copy per task.
        if(depth>=source.H && bound>=source.Nodes[source.Nodes.Length-1].T)return source.Nodes;
        var key=(bound,Math.Min(depth,source.H));
        if(!source.CandidateViews.TryGetValue(key,out var view)) {
            view=source.Nodes.Where(n=>n.T<=bound && n.H<=depth).ToArray();
            source.CandidateViews[key]=view;
        }
        return view;
    }
    static long CombinationEstimate(int count) {
        double sum=0,n=count,pairs=n*(n+1)/2;
        for(int g=0;g<21;g++)if(Enabled[g]&&g!=1) {
            if(g==14)sum+=n*n*n;
            else if(g==9||g==10)sum+=pairs*n;
            else if(g==15||g==16)sum+=pairs*(pairs+1)/2;
            else {double tuples=1;for(int k=1;k<=Arity[g];k++)tuples*=((n+k-1)/k);sum+=tuples;}
        }
        return (long)Math.Min(long.MaxValue/2,sum);
    }
    static void ImageJob(Frontier source,int g) {
        var tuples=Tuples(g,source.Nodes.Length,Arity[g]).GetEnumerator();int chunks=0;
        Enqueue("image",$"frontier={source.Id} gate={Names[g]}",source.Nodes.Last().T+Cost[g],()=> {
            for(int k=0;k<256;k++) {
                if(!tuples.MoveNext())return true;
                var a=tuples.Current.Select(i=>source.Nodes[i]).ToArray();
                ArchiveNode(Compose(g,a));
            }
            ImageChunks++;chunks++;
            // Avoid endlessly enumerating a full archive. This is a resource
            // stop for discovery, not completion of the function image.
            return Stored>=Config.MaxStates;
        });
    }
    static void CoverJobs(Frontier source) {
        if(source.H+1>WholeLimit)return;
        for(int j=0;j<Target.Length;j++)for(int family=0;family<4;family++) {
            int output=j,fam=family;
            var roots=Families[fam].Where(g=>Enabled[g]).ToArray();if(roots.Length==0)continue;
            ulong wanted=(fam==0||fam==3)?Target[j]:~Target[j];bool complement=fam<2;
            if(wanted==0)continue; // constants remain covered by general queries
            if(!CoverArchive.TryGetValue((j,fam),out var covers))CoverArchive[(j,fam)]=covers=new Covers();
            var pool=covers.Pool;
            AddBase(source.Map,wanted,complement,pool);
            Action<int> schedule=childCeiling=> {
                long sum=pool.Values.Sum(n=>(long)n.T);
                foreach(int root in roots) {
                    // Discovery asks for any improvement using the accumulated
                    // pool. Enumerating every tighter generation deadline here
                    // duplicates proof-like NO work before exploiting a SAT.
                    int limit=Best[output]==null?(pool.Count==0?childCeiling:pool.Values.Max(n=>n.T)):Best[output].T-Cost[root]-1;
                    var query=(pool.Count,sum,root,limit);
                    if(covers.NegativeQueries.Contains(query)) {CoverHits++;continue;}
                    if(limit<MinCost||!covers.Pending.Add((root,0)))continue;
                    int gate=root;
                    // Every root and deadline is its own task. A difficult
                    // low-arity NO must not block a different root's SAT.
                    int estimate=(pool.Count==0?MinCost:pool.Values.Min(n=>n.T))+Cost[gate];
                    Enqueue("cover",$"output={output} root={Names[gate]} incumbent_query",estimate,()=> {
                        int deadline=Best[output]==null?(pool.Count==0?childCeiling:pool.Values.Max(n=>n.T)):Best[output].T-Cost[gate]-1;
                        var current=(pool.Count,pool.Values.Sum(n=>(long)n.T),gate,deadline);
                        if(!covers.NegativeQueries.Contains(current)) {
                            Node n=FindCover(pool,wanted,gate,deadline,witness=> {
                                if(witness.H<=WholeLimit) {ArchiveNode(witness);Improve(output,witness,"adaptive cover witness");}
                            });
                            if(n!=null && n.H<=WholeLimit) {ArchiveNode(n);Improve(output,n,"adaptive relation cover");}
                            else if(n==null)covers.NegativeQueries.Add(current);
                        } else CoverHits++;
                        covers.Pending.Remove((gate,0));return true;
                    },output);
                }
            };
            schedule(source.Nodes.Last().T);
            if(source.H+2>WholeLimit)continue;
            foreach(int b in source.Nodes.Select(n=>n.T).Distinct().OrderBy(t=>t))
            for(int g=0;g<21;g++)if(Enabled[g]&&g!=1) {
                int gate=g,budget=b;
                Enqueue("demand",$"frontier={source.Id} output={j} family={fam} gate={Names[g]} budget={b}",
                    b+Cost[g]+roots.Min(r=>Cost[r]),()=> {
                    int limit=Best[output]==null?budget:Math.Min(budget,Best[output].T-roots.Min(r=>Cost[r])-Cost[gate]-1);
                    if(limit<MinCost)return true;
                    int count=Array.FindIndex(source.Nodes,n=>n.T>limit);if(count<0)count=source.Nodes.Length;
                    int token=DomainToken(source,count);
                    var key=(token,output,fam,gate);
                    if(Generated.Contains(key)) {GenerationHits++;schedule(limit+Cost[gate]);return true;}
                    var eligible=source.Nodes.Take(count).ToDictionary(n=>n.F,n=>n,TruthKeys);
                    int before=pool.Count;
                    // The accelerated kernel may be interrupted; accumulated
                    // valid witnesses remain available and the task is retried.
                    try {AddMiddle(eligible,wanted,complement,gate,pool);Generated.Add(key);}
                    finally {
                        foreach(var n in pool.Values)ArchiveNode(n);
                        if(pool.Count!=before || before>0)schedule(limit+Cost[gate]);
                    }
                    return true;
                },output);
            }
        }
    }
    static void Publish(int depth,bool force=false) {
        if(depth<1||depth>WholeLimit)return;
        var previous=Frontiers.LastOrDefault(f=>f.H==depth);
        if(previous!=null&&!Config.AdaptiveRefresh&&!force)return;
        var map=new Dictionary<ulong,Node>(TruthKeys);
        foreach(var level in Archive.Where(v=>v.Key<=depth))foreach(var n in level.Value.Values)
            if(!map.TryGetValue(n.F,out var old)||n.T<old.T)map[n.F]=n;
        if(map.Count==0)return;
        PublishedRevisions[depth]=LevelRevisions.Where(v=>v.Key<=depth).Sum(v=>v.Value);
        if(previous!=null && map.Count==previous.Map.Count && map.All(v=>previous.Map.TryGetValue(v.Key,out var old)&&old.T==v.Value.T&&old.H==v.Value.H))return;
        if(previous!=null)FrontierRefreshes++;
        var source=new Frontier{Id=Frontiers.Count,H=depth,Map=map,Nodes=map.Values.OrderBy(n=>n.T).ThenBy(n=>n.F).ToArray()};
        // Normal in-memory indexing, with full equality checks on collisions;
        // no file hashes, historical signatures or externally supplied cache.
        source.Prefix=new ulong[source.Nodes.Length+1];source.Prefix[0]=14695981039346656037UL;
        unchecked {for(int i=0;i<source.Nodes.Length;i++) {
            Node n=source.Nodes[i];ulong h=source.Prefix[i];
            h=(h^n.F)*1099511628211UL;h=(h^(ulong)n.T)*1099511628211UL;h=(h^(ulong)n.H)*1099511628211UL;
            source.Prefix[i+1]=h;
        }}
        source.Index=new MatchIndex(source.Nodes);Frontiers.Add(source);
        Record(new{event_type="frontier",source.Id,depth,functions=map.Count,refresh=previous!=null,seconds=Watch.Elapsed.TotalSeconds});
        for(int j=0;j<Target.Length;j++) {
            int output=j;
            int bound=Best[j]==null?source.Nodes.Last().T+Enabled.Select((v,g)=>v?Cost[g]:0).Max():Best[j].T-1;
            int h=Math.Min(WholeLimit,bound/MinCost);
            var need=new Need{Value=Target[j],Care=~0UL,Bound=bound,H=h,Output=j};need.Users.Add(n=>Improve(output,n,"adaptive general root"));
            for(int g=0;g<21;g++)if(Enabled[g]&&g!=1)QueryJob(source,need,g,"match");
        }
        if(Config.AdaptiveCovers)CoverJobs(source);
        if(depth<WholeLimit) {
            if(CombinationEstimate(map.Count)<=Config.MaxStates) {
                int ceiling=Math.Max(Cost[0],Cost[1])+depth*Enabled.Select((v,g)=>v?Cost[g]:0).Max();
                Enqueue("library",$"complete depth={depth+1}",MinCost,()=> {
                    var next=Library(ceiling,depth+1);
                    foreach(var n in next.Values)ArchiveNode(n);
                    if(next.Count>map.Count || next.Any(v=>!map.TryGetValue(v.Key,out var old)||old.T>v.Value.T))Publish(depth+1);
                    return true;
                });
            } else for(int g=0;g<21;g++)if(Enabled[g]&&g!=1)ImageJob(source,g);
        }
    }
    static Node ParseInitial(JsonElement e) {
        var args=e.EnumerateArray().ToArray();int g=Array.IndexOf(Names,args[0].GetString());
        if(g<0||!Enabled[g])throw new ArgumentException("Invalid initial gate");
        if(args.Length!=Arity[g]+1)throw new ArgumentException("Invalid initial arity");
        if(args.Length==2 && args[1].ValueKind==JsonValueKind.String) {
            if(g!=0&&g!=1)throw new ArgumentException("Unpaid initial input");
            string name=args[1].GetString();
            if(!name.StartsWith("x")||!int.TryParse(name.Substring(1),out int x)||x<0||x>=Inputs.Length)
                throw new ArgumentException("Invalid initial input");
            return MakeSeed(g,x);
        }
        return Compose(g,args.Skip(1).Select(ParseInitial).ToArray());
    }
    static int ExchangeVersion=-1,ExchangeImports,ExchangeExports;
    static double ExchangeAt=-1;
    static int LastExportAdded=-1,LastExportAck=-2,LastExportImports=-1;
    static string LastExportSignals;
    static (DateTime,long)? LastExchangeInput;
    static object NodeExpression(Node n) => n.X>=0
        ?new object[]{Names[n.G],"x"+n.X}
        :new object[]{Names[n.G]}.Concat(n.A.Select(NodeExpression)).ToArray();
    static void ArchiveTree(Node n,HashSet<Node> seen) {
        if(!seen.Add(n))return;
        foreach(var child in n.A)ArchiveTree(child,seen);
        ArchiveNode(n);
    }
    // Import only at dispatch boundaries: archive mutation is never interleaved
    // with a kernel's collection traversal. Every imported expression is evaluated.
    static void ExchangeStep() {
        if(!Config.Exchange||Watch.Elapsed.TotalSeconds<ExchangeAt)return;
        ExchangeAt=Watch.Elapsed.TotalSeconds+0.5;
        string path=Path.Combine(Output,"exchange_in.json");
        if(File.Exists(path)) {
            var info=new FileInfo(path);
            var stamp=(info.LastWriteTimeUtc,info.Length);
            if(LastExchangeInput!=stamp) {
                string message;
                try {message=File.ReadAllText(path);}
                catch(IOException) {return;}
                catch(UnauthorizedAccessException) {return;}
                using var document=JsonDocument.Parse(message);
                var root=document.RootElement;int version=root.GetProperty("version").GetInt32();
                if(version>ExchangeVersion) {
                    int before=Added;var seen=new HashSet<Node>();
                    foreach(var item in root.GetProperty("expressions").EnumerateObject()) {
                        int j=int.Parse(item.Name);Node n=ParseInitial(item.Value);
                        if(j<0||j>=Target.Length||n.F!=Target[j]||n.H>WholeLimit)
                            throw new ArgumentException("Invalid exchange candidate");
                        if(Best[j]==null||n.T<Best[j].T) {
                            Improve(j,n,"unified feedback");ArchiveTree(n,seen);ExchangeImports++;
                        }
                    }
                    ExchangeVersion=version;
                    if(Added>before) {
                        // Fresh snapshots retain all old jobs, whose own incumbent
                        // checks see the new bound. No stale negative cache is reused.
                        foreach(int depth in Frontiers.Select(f=>f.H).Distinct().ToArray())Publish(depth,true);
                        // A deep imported witness must not move the exploration
                        // frontier past unbuilt shallow domains. Its children are
                        // archived now and enter normal later depth publications.
                    }
                }
                LastExchangeInput=stamp;
            }
        }
        if(LastExportAdded==Added && LastExportAck==ExchangeVersion && LastExportImports==ExchangeImports)return;
        var signals=Archive.OrderBy(v=>v.Key).SelectMany(v=>v.Value.Values.OrderBy(n=>n.T).ThenBy(n=>n.F).Take(24))
            .Where(n=>n.H<=12).Take(192).Select(NodeExpression).ToArray();
        string encoded=JsonSerializer.Serialize(signals);
        LastExportAdded=Added;
        if(encoded==LastExportSignals && LastExportAck==ExchangeVersion && LastExportImports==ExchangeImports)return;
        WriteJson("exchange_out.json",new{version=++ExchangeExports,ack=ExchangeVersion,
            imports=ExchangeImports,signals});
        LastExportSignals=encoded;LastExportAck=ExchangeVersion;LastExportImports=ExchangeImports;
    }
    static int RunAdaptive() {
        TraceBytes=TraceRecords=TraceSkipped=TraceFlushes=0;TraceLimitReached=false;LastTraceFlush=0;
        Trace=Config.DecisionLogMaxBytes==0?null:
            new StreamWriter(Path.Combine(Output,"decisions.jsonl"),false,new UTF8Encoding(false),64*1024);
        if(Trace!=null)Trace.NewLine="\n";
        try {
            if(Config.MaxStates<1||Config.WholeDepth<0)throw new ArgumentException("Invalid adaptive limits");
            if(Config.Initial.ValueKind==JsonValueKind.Object)foreach(var p in Config.Initial.EnumerateObject()) {
                int j=int.Parse(p.Name);Node n=ParseInitial(p.Value);
                if(n.F!=Target[j])throw new ArgumentException("Invalid initial target");
                if(n.H<=WholeLimit) {Best[j]=n;BestVersion++;}
            }
            for(int x=0;x<Inputs.Length;x++) {ArchiveNode(MakeSeed(0,x));ArchiveNode(MakeSeed(1,x));}
            Publish(1);Save();int publishedAt=Added;
            while(Agenda.Count>0||Config.Exchange) {
                Check();ExchangeStep();
                if(Agenda.Count==0) {Save();System.Threading.Thread.Sleep(20);continue;}
                Turn++;
                // A dispatch-count quota gives almost all wall time to slow
                // exploration kernels when other tasks take microseconds.
                Work job=NextWork(out bool fair,out bool discovery);int before=Added,old=BestCostSum(),foundBefore=Best.Count(n=>n!=null);
                double progressBefore=NeedProgress,start=Watch.Elapsed.TotalSeconds;
                bool done=false,timedOut=false;
                SliceDeadline=start+Config.SliceSeconds*Math.Pow(2,Math.Min(job.Attempts,8));
                if(Config.Exchange)SliceDeadline=Math.Min(SliceDeadline,start+15);
                try {done=ExecuteWork(job);}
                catch(SliceException) {timedOut=true;SliceStops++;job.Attempts++;}
                catch(AggregateException e) when(e.Flatten().InnerExceptions.All(x=>x is SliceException)) {timedOut=true;SliceStops++;job.Attempts++;}
                finally {SliceDeadline=double.PositiveInfinity;}
                double elapsed=Watch.Elapsed.TotalSeconds-start;
                WorkSeconds+=elapsed;if(fair)FairSeconds+=elapsed;
                if(IsDiscovery(job.Kind))DiscoverySeconds+=elapsed;
                // Account for spent retries too, but more gently than resumable
                // chunks: a restart still needs a larger quantum to finish.
                job.Services++;
                // Novel states are a diagnostic, not a reward: rewarding their
                // count can starve a ready target query behind blind expansion.
                double gain=Math.Max(0,old-BestCostSum())/(double)Math.Max(1,MinCost)
                    +Math.Max(0,Best.Count(n=>n!=null)-foundBefore)+NeedProgress-progressBefore;
                double observed=gain/Math.Max(0.01,elapsed);
                YieldRate[job.Kind]=YieldRate.TryGetValue(job.Kind,out var previous)?0.8*previous+0.2*observed:observed;
                Runs[job.Kind]=Runs.TryGetValue(job.Kind,out int n)?n+1:1;
                OperatorSeconds[job.Kind]=(OperatorSeconds.TryGetValue(job.Kind,out double spent)?spent:0)+elapsed;
                if(done||timedOut||Added>before||Turn%128==0)Record(new{event_type="work",turn=Turn,job.Id,job.Kind,job.Detail,job.Estimate,job.Output,
                    selection=fair?"waiting_task":"cost_and_measured_yield",reserved_cover_discovery=discovery,seconds=elapsed,added=Added-before,
                    completed=done,timed_out=timedOut,attempts=job.Attempts,queued=Agenda.Count});
                if(!done)Schedule(job);
                if(Turn%32==0) {
                    Save();
                    if(Config.AdaptiveRefresh && Turn%256==0) {
                        foreach(var frontier in Frontiers.GroupBy(f=>f.H).Select(g=>g.Last()).OrderBy(f=>f.H).ToArray()) {
                            int revision=LevelRevisions.Where(v=>v.Key<=frontier.H).Sum(v=>v.Value);
                            if(revision-PublishedRevisions[frontier.H]>=Math.Max(128,frontier.Nodes.Length/2)) {
                                Publish(frontier.H);break;
                            }
                        }
                    }
                    int next=Frontiers.Max(f=>f.H)+1;
                    if(next<=WholeLimit && Added-publishedAt>=Math.Max(128,Frontiers.Last().Nodes.Length/2) && Archive.ContainsKey(next)) {
                        Publish(next);publishedAt=Added;
                    }
                }
            }
            Status=Best.All(n=>n!=null)?"FEASIBLE":"INCOMPLETE";Reason="Discovery agenda exhausted; no optimality claim";
        } catch(StopException e) {Status=Best.All(n=>n!=null)?"FEASIBLE":"INCOMPLETE";Reason=e.Message;}
        catch(OutOfMemoryException) {
            GC.Collect();Status=Best.All(n=>n!=null)?"FEASIBLE":"INCOMPLETE";
            Reason="native allocation budget reached; unfinished queries are UNKNOWN";
        }
        catch(Exception e) {Status="ERROR";Reason=e.GetType().Name;}
        finally {
            SliceDeadline=double.PositiveInfinity;Save(true);FlushTrace(true);
            WriteJson("adaptive.json",new{status=Status,reason=Reason,seconds=Watch.Elapsed.TotalSeconds,
                resource_stop=Reason!=null && (Reason.StartsWith("native memory budget") || Reason.StartsWith("native allocation budget"))?Reason:null,
                whole_depth=Config.WholeDepth,archive_states=Stored,archive_drops=ArchiveDrops,request_drops=NeedDrops,
                exchange_imports=ExchangeImports,exchange_exports=ExchangeExports,exchange_ack=ExchangeVersion,
                requests=Needs.Count,frontiers=Frontiers.Select(f=>new{depth=f.H,functions=f.Nodes.Length}),
                actions=Turn,operator_runs=Runs,measured_yields=YieldRate,image_chunks=ImageChunks,root_checks=RootChecks,
                operator_seconds=OperatorSeconds,
                kernel_seconds=WorkSeconds,exploration_seconds=FairSeconds,
                generation_cache_hits=GenerationHits,cover_query_cache_hits=CoverHits,
                resolved_demand_progress=NeedProgress,
                frontier_refreshes=FrontierRefreshes,refresh_enabled=Config.AdaptiveRefresh,
                decision_log=new {enabled=Config.DecisionLogMaxBytes>0,max_bytes=Config.DecisionLogMaxBytes,
                    bytes_written=TraceBytes,records_written=TraceRecords,records_skipped=TraceSkipped,
                    limit_reached=TraceLimitReached},
                remaining_tasks=Agenda.Count,global_optimality_proved=false,
                scheduler=AdaptiveProgress(),
                memory=new {rss_bytes=Environment.WorkingSet,heap_bytes=GC.GetTotalMemory(false),
                    rss_budget_bytes=Config.RssBudgetBytes,heap_soft_bytes=Config.HeapSoftBytes,
                    cover_memo_resets=CoverMemoResets,query_allocation_retries=MemoryRetries,
                    collections=MemoryCollections,queue_compactions=QueueCompactions,
                    request_memory_deferrals=RequestMemoryDeferrals,
                    priority_queue_entries=QueueEntries,waiting_queue_entries=Waiting.Count},
                io=new {json_writes=JsonWrites,incumbent_writes=IncumbentWrites,
                    progress_writes=ProgressWrites,exchange_writes=ExchangeExports,
                    decision_log_flushes=TraceFlushes}});
            Trace?.Dispose();
        }
        OnProgress(Status);return Status=="ERROR"?1:Best.All(n=>n!=null)?0:2;
    }
}
