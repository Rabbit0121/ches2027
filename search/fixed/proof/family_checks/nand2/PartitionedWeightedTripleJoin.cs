using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
public static class PartitionedWeightedTripleJoin {
 sealed class Hash:IEqualityComparer<ulong>{public bool Equals(ulong x,ulong y)=>x==y;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return(int)x;}}}
 struct Row {public ulong F;public int T,Id;}
 struct Node {public ulong Bad,Good;public int L,R,Start,End;}
 static Row[] rows;static Node[] tree;static int nodes,threshold,seconds;static ulong target,bad,sortmask;static long visits,triples;static bool limited;static string output;static System.Diagnostics.Stopwatch clock;
 static Dictionary<ulong,(int t,int a,int b,int c)> found;
 static int[][] wt;static bool stopFirst;
 static void InitWeights(){var ws=new int[64];using(var r=new BinaryReader(File.OpenRead(Environment.GetEnvironmentVariable("NAND3_WEIGHTS_PATH"))))for(int i=0;i<64;i++){ws[i]=r.ReadInt32();if(ws[i]<0)throw new Exception("negative weight");}wt=new int[4][];for(int k=0;k<4;k++){wt[k]=new int[65536];for(int j=1;j<65536;j++)wt[k][j]=wt[k][j&(j-1)]+ws[16*k+BitOperations.TrailingZeroCount((uint)j)];}stopFirst=Environment.GetEnvironmentVariable("NAND3_STOP_FIRST")=="1";}
 static int Weight(ulong x){return wt[0][(int)(x&65535)]+wt[1][(int)((x>>16)&65535)]+wt[2][(int)((x>>32)&65535)]+wt[3][(int)(x>>48)];}

 static int Build(int lo,int hi){int ix=nodes++;Node n=new Node{Start=lo,End=hi,L=-1,R=-1,Bad=ulong.MaxValue};if(hi-lo==1){n.Bad=rows[lo].F&bad;n.Good=rows[lo].F&target;}else{ulong x=(rows[lo].F^rows[hi-1].F)&sortmask;if(x==0)x=rows[lo].F^rows[hi-1].F;if(x==0)throw new Exception("duplicate truth");int bit=63-BitOperations.LeadingZeroCount(x);int a=lo,b=hi;while(a<b){int m=(a+b)>>1;if(((rows[m].F>>bit)&1)==0)a=m+1;else b=m;}if(a<=lo||a>=hi)throw new Exception("split");n.L=Build(lo,a);n.R=Build(a,hi);n.Bad=tree[n.L].Bad&tree[n.R].Bad;n.Good=tree[n.L].Good|tree[n.R].Good;}tree[ix]=n;return ix;}
 static void Save(){using(var w=new BinaryWriter(File.Create(output))){w.Write(found.Count);foreach(var kv in found){w.Write(kv.Key);w.Write(kv.Value.t);w.Write(kv.Value.a);w.Write(kv.Value.b);w.Write(kv.Value.c);}}File.WriteAllText(output+".json",$"{{\"status\":\"{(stopFirst&&found.Count>0?"SAT":limited?"PARTIAL":"COMPLETE")}\",\"inputs\":{rows.Length},\"nodes\":{nodes},\"threshold\":{threshold},\"covers\":{found.Count},\"visits\":{visits},\"triples\":{triples},\"seconds\":{clock.Elapsed.TotalSeconds}}}");}
 static void Join(int a,int b,int c){
  if(limited)return;if(a>b){int z=a;a=b;b=z;}if(b>c){int z=b;b=c;c=z;}if(a>b){int z=a;a=b;b=z;}
  visits++;if(visits%10000000==0){Console.WriteLine($"visits={visits} triples={triples} covers={found.Count} seconds={clock.Elapsed.TotalSeconds:F2}");if(seconds>0&&clock.Elapsed.TotalSeconds>seconds){limited=true;return;}}
  ref Node x=ref tree[a];ref Node y=ref tree[b];ref Node zc=ref tree[c];
  if((x.Bad&y.Bad&zc.Bad)!=0||Weight(x.Good&y.Good&zc.Good)<threshold)return;
  if(x.L<0&&y.L<0&&zc.L<0){triples++;Row p=rows[x.Start],q=rows[y.Start],r=rows[zc.Start];ulong f=p.F&q.F&r.F;int t=Math.Max(p.T,Math.Max(q.T,r.T))+34767;if((f&bad)!=0||Weight(f)<threshold)throw new Exception("bad triple");if(!found.TryGetValue(f,out var old)||t<old.t)found[f]=(t,p.Id,q.Id,r.Id);if(stopFirst)limited=true;return;}
  int split=a;int size=x.L<0?0:x.End-x.Start;if(y.L>=0&&y.End-y.Start>size){split=b;size=y.End-y.Start;}if(zc.L>=0&&zc.End-zc.Start>size)split=c;
  int l=tree[split].L,rn=tree[split].R;if(l<0)throw new Exception("leaf split");
  if(a==b&&b==c){Join(l,l,l);Join(l,l,rn);Join(l,rn,rn);Join(rn,rn,rn);}
  else if(a==b&&split==a){Join(l,l,c);Join(l,rn,c);Join(rn,rn,c);}
  else if(b==c&&split==b){Join(a,l,l);Join(a,l,rn);Join(a,rn,rn);}
  else if(split==a){Join(l,b,c);Join(rn,b,c);}else if(split==b){Join(a,l,c);Join(a,rn,c);}else{Join(a,b,l);Join(a,b,rn);}
 }

 static (int,int,int) Canon(int a,int b,int c){if(a>b){int x=a;a=b;b=x;}if(b>c){int x=b;b=c;c=x;}if(a>b){int x=a;a=b;b=x;}return(a,b,c);}
 static bool Alive((int,int,int)q){Node a=tree[q.Item1],b=tree[q.Item2],c=tree[q.Item3];return(a.Bad&b.Bad&c.Bad)==0&&Weight(a.Good&b.Good&c.Good)>=threshold;}
 static List<(int,int,int)> Children((int,int,int)q){int ai=q.Item1,bi=q.Item2,ci=q.Item3;Node a=tree[ai],b=tree[bi],c=tree[ci];int at=ai,size=a.L<0?0:a.End-a.Start;if(b.L>=0&&b.End-b.Start>size){at=bi;size=b.End-b.Start;}if(c.L>=0&&c.End-c.Start>size)at=ci;if(tree[at].L<0)return null;int l=tree[at].L,r=tree[at].R;var v=new List<(int,int,int)>();if(ai==bi&&bi==ci){v.Add(Canon(l,l,l));v.Add(Canon(l,l,r));v.Add(Canon(l,r,r));v.Add(Canon(r,r,r));}else if(ai==bi&&at==ai){v.Add(Canon(l,l,ci));v.Add(Canon(l,r,ci));v.Add(Canon(r,r,ci));}else if(bi==ci&&at==bi){v.Add(Canon(ai,l,l));v.Add(Canon(ai,l,r));v.Add(Canon(ai,r,r));}else if(at==ai){v.Add(Canon(l,bi,ci));v.Add(Canon(r,bi,ci));}else if(at==bi){v.Add(Canon(ai,l,ci));v.Add(Canon(ai,r,ci));}else{v.Add(Canon(ai,bi,l));v.Add(Canon(ai,bi,r));}return v;}
 static int startTask,nextTask,totalTasks;
 static void TaskProgress(){File.WriteAllText(output+".tasks.json",$"{{\"start_task\":{startTask},\"next_task\":{nextTask},\"total_tasks\":{totalTasks},\"complete_tasks_this_run\":{nextTask-startTask},\"status\":\"{(found.Count>0?"SAT":nextTask==totalTasks?"COMPLETE_SUFFIX":"PARTIAL")}\",\"seconds\":{clock.Elapsed.TotalSeconds},\"visits\":{visits}}}");}
 static void RunFrontier(){var front=new List<(int,int,int)>();if(rows.Length>0&&Alive((0,0,0)))front.Add((0,0,0));int goal=int.TryParse(Environment.GetEnvironmentVariable("NAND3_FRONTIER_SIZE"),out int q)?q:8192;
  while(front.Count>0&&front.Count<goal){bool changed=false;var nf=new List<(int,int,int)>();foreach(var v in front){var ch=Children(v);if(ch==null)nf.Add(v);else{changed=true;foreach(var u in ch)if(Alive(u))nf.Add(u);}}front=nf;if(!changed)break;}
  totalTasks=front.Count;startTask=int.TryParse(Environment.GetEnvironmentVariable("NAND3_START_TASK"),out int s)?s:0;if(startTask<0||startTask>totalTasks)throw new Exception("bad start");nextTask=startTask;
  using(var w=new BinaryWriter(File.Create(output+".frontier"))){w.Write(front.Count);foreach(var q2 in front){w.Write(q2.Item1);w.Write(q2.Item2);w.Write(q2.Item3);}}Console.WriteLine($"frontier={totalTasks} start={startTask}");
  for(int i=startTask;i<totalTasks;i++){if(seconds>0&&clock.Elapsed.TotalSeconds>seconds){limited=true;break;}var v=front[i];Join(v.Item1,v.Item2,v.Item3);if(limited)break;nextTask=i+1;if(nextTask%100==0){Console.WriteLine($"completed={nextTask}/{totalTasks} visits={visits} seconds={clock.Elapsed.TotalSeconds:F2}");TaskProgress();}}
  TaskProgress();
 }
 public static void Run(string input,string outpath,ulong goal,int minimum,int limit){RunOrdered(input,outpath,goal,minimum,limit,false);}
 public static void RunGood(string input,string outpath,ulong goal,int minimum,int limit){RunOrdered(input,outpath,goal,minimum,limit,true);}
 public static void RunOrdered(string input,string outpath,ulong goal,int minimum,int limit,bool goodfirst){InitWeights();target=goal;bad=~goal;sortmask=goodfirst?target:bad;threshold=minimum;seconds=limit;output=outpath;nodes=0;visits=triples=0;limited=false;clock=System.Diagnostics.Stopwatch.StartNew();found=new Dictionary<ulong,(int,int,int,int)>(new Hash());var data=new List<Row>();using(var r=new BinaryReader(File.OpenRead(input))){int n=r.ReadInt32();for(int i=0;i<n;i++){ulong f=r.ReadUInt64();int t=r.ReadInt32();if(Weight(f&target)>=threshold)data.Add(new Row{F=f,T=t,Id=i});}}
  rows=data.ToArray();Array.Sort(rows,(a,b)=>{int k=(a.F&sortmask).CompareTo(b.F&sortmask);return k!=0?k:a.F.CompareTo(b.F);});tree=new Node[Math.Max(1,rows.Length*2)];if(rows.Length>0)Build(0,rows.Length);Console.WriteLine($"built inputs={rows.Length} nodes={nodes}");RunFrontier();Save();
 }
}
