using System;
using System.IO;
using System.Numerics;
using System.Collections.Generic;
public static class GlobalAoiFull {
 // UInt64.GetHashCode folds equal 32-bit truth-table halves to zero.
 // Thousands of <=5-variable functions collide under that default hash.
 sealed class TruthHash : IEqualityComparer<ulong> {
  public bool Equals(ulong a,ulong b)=>a==b;
  public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return (int)(x^(x>>32));}}
 }
 struct Node {public ulong Or,And;public int L,R,Bit,Pop;}
 static Node[] nodes;static ulong[] keys;static int count;
 static int Build(int lo,int hi){int at=count++;Node n=new Node{L=-1,R=-1};if(hi-lo==1){n.Or=n.And=keys[lo];n.Pop=BitOperations.PopCount(keys[lo]);}else{n.Bit=63-BitOperations.LeadingZeroCount(keys[lo]^keys[hi-1]);ulong edge=(keys[lo]&(~0UL<<n.Bit))|(1UL<<n.Bit);int a=lo,b=hi;while(a<b){int m=(a+b)>>1;if(keys[m]<edge)a=m+1;else b=m;}n.L=Build(lo,a);n.R=Build(a,hi);n.Or=nodes[n.L].Or|nodes[n.R].Or;n.And=nodes[n.L].And&nodes[n.R].And;n.Pop=Math.Max(nodes[n.L].Pop,nodes[n.R].Pop);}nodes[at]=n;return at;}
 static bool StrictSuper(int at,ulong f,int pop){ref Node n=ref nodes[at];if(n.Pop<=pop||(n.Or&f)!=f)return false;if((n.And&f)==f)return true;if(n.L<0)return false;if(((f>>n.Bit)&1)!=0)return StrictSuper(n.R,f,pop);return StrictSuper(n.R,f,pop)||StrictSuper(n.L,f,pop);}

 struct Rec { public int T,G,A,B,C,E; public Rec(int t,int g,int a,int b=-1,int c=-1,int e=-1){T=t;G=g;A=a;B=b;C=c;E=e;} }
 static readonly string[] Names={"INV","BUF","NAND2","NOR2","AND2","OR2","XOR2","XNOR2","NAND3","OAI21","AOI21","NOR3","AND3","OR3","MUX2","OAI22","AOI22","NAND4","NOR4","AND4","OR4"};
 static readonly int[] Costs={22048,33557,27886,40650,40171,56414,73019,57604,34767,32651,51619,61543,51869,85840,75175,54596,57255,44487,91313,65492,118592};
 public static ulong Eval(int g,ulong a,ulong b,ulong c,ulong e) => g switch {
 0=>~a,1=>a,2=>~(a&b),3=>~(a|b),4=>a&b,5=>a|b,6=>a^b,7=>~(a^b),8=>~(a&b&c),9=>~((a|b)&c),10=>~((a&b)|c),11=>~(a|b|c),12=>a&b&c,13=>a|b|c,14=>(a&~c)|(b&c),15=>~((a|b)&(c|e)),16=>~((a&b)|(c&e)),17=>~(a&b&c&e),18=>~(a|b|c|e),19=>a&b&c&e,20=>a|b|c|e,_=>throw new Exception()};
 public static void Run(string input,string output,int bound,ulong target,string centers) {
  var allowed=new HashSet<ulong>(new TruthHash());using(var cr=new BinaryReader(File.OpenRead(centers))){int cn=cr.ReadInt32();for(int i=0;i<cn;i++){ulong s=cr.ReadUInt64(),q=s;if((s&~target)!=0)throw new Exception("bad center");while(true){allowed.Add(q);if(q==0)break;q=(q-1)&s;}}}Console.WriteLine("downset="+allowed.Count);
  int n;ulong[] fs;int[] ts;
  using(var r=new BinaryReader(File.OpenRead(input))){n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();}}
  var records=new Dictionary<ulong,Rec>(new TruthHash());for(int i=0;i<n;i++)if(ts[i]<=bound&&allowed.Contains(fs[i]&target)){ulong p=fs[i];if(!records.TryGetValue(p,out var old)||ts[i]<old.T)records[p]=new Rec(ts[i],-1,i);}
  var watch=System.Diagnostics.Stopwatch.StartNew();long tuples=0;bool found=false;ulong w1=0,w2=0;
  void Add(int g,int a,int b=-1,int c=-1,int e=-1){
   ulong f=Eval(g,fs[a],b<0?0:fs[b],c<0?0:fs[c],e<0?0:fs[e]);int t=ts[a];if(b>=0)t=Math.Max(t,ts[b]);if(c>=0)t=Math.Max(t,ts[c]);if(e>=0)t=Math.Max(t,ts[e]);t+=Costs[g];tuples++;if(!allowed.Contains(f&target))return;
   if(!records.TryGetValue(f,out var old)||t<old.T){records[f]=new Rec(t,g,a,b,c,e);}
  }
  for(int g=0;g<Names.Length&&!found;g++){if(!(g==10||g==15||g==16))continue;
   var ids=new List<int>();for(int i=0;i<n;i++)if(ts[i]+Costs[g]<=bound)ids.Add(i);int m=ids.Count;
   if(g<=1){for(int a=0;a<m&&!found;a++)Add(g,ids[a]);}
   else if(g<=7){for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)Add(g,ids[a],ids[b]);}
   else if(g==9||g==10){for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)for(int c=0;c<m;c++)Add(g,ids[a],ids[b],ids[c]);}
   else if(g==14){for(int a=0;a<m&&!found;a++)for(int b=0;b<m;b++)for(int c=0;c<m;c++)Add(g,ids[a],ids[b],ids[c]);}
   else if(g<15){for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)for(int c=b;c<m;c++)Add(g,ids[a],ids[b],ids[c]);}
   else if(g==15||g==16){var pd=new Dictionary<ulong,(int t,int a,int b)>(new TruthHash());for(int a=0;a<m;a++)for(int b=a;b<m;b++){int ia=ids[a],ib=ids[b],t=Math.Max(ts[ia],ts[ib]);ulong f=g==15?fs[ia]|fs[ib]:fs[ia]&fs[ib];if(!pd.TryGetValue(f,out var old)||t<old.t)pd[f]=(t,ia,ib);}var pp0=new List<KeyValuePair<ulong,(int t,int a,int b)>>();foreach(var q in pd)if(g!=15||allowed.Contains((~q.Key)&target))pp0.Add(q);keys=new ulong[pp0.Count];for(int i=0;i<keys.Length;i++)keys[i]=(~pp0[i].Key)^target;Array.Sort(keys);nodes=new Node[Math.Max(1,keys.Length*2)];count=0;if(keys.Length>0)Build(0,keys.Length);var pp=new List<KeyValuePair<ulong,(int t,int a,int b)>>();foreach(var q in pp0){ulong k=(~q.Key)^target;if(!StrictSuper(0,k,BitOperations.PopCount(k)))pp.Add(q);}Console.WriteLine("symbolic original="+pd.Count+" admissible="+pp0.Count+" mixedmax="+pp.Count);Console.WriteLine("symbolic "+Names[g]+" pairs="+pp.Count);for(int a=0;a<pp.Count;a++)for(int b=a;b<pp.Count;b++){ulong f=g==15?~(pp[a].Key&pp[b].Key):~(pp[a].Key|pp[b].Key);tuples++;if(!allowed.Contains(f&target))continue;int t=Math.Max(pp[a].Value.t,pp[b].Value.t)+Costs[g];if(!records.TryGetValue(f,out var old)||t<old.T)records[f]=new Rec(t,g,pp[a].Value.a,pp[a].Value.b,pp[b].Value.a,pp[b].Value.b);}}
   else{for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)for(int c=b;c<m;c++)for(int e=c;e<m;e++)Add(g,ids[a],ids[b],ids[c],ids[e]);}
   string progress=$"{Names[g]} inputs={m} states={records.Count} tuples={tuples} seconds={watch.Elapsed.TotalSeconds:F2} found={found}";
   Console.WriteLine(progress);File.AppendAllText(output+".progress.log",progress+Environment.NewLine);
  }
  void Write(BinaryWriter w,ulong f,Rec q){w.Write(f);w.Write(q.T);w.Write(q.G);w.Write(q.A);w.Write(q.B);w.Write(q.C);w.Write(q.E);}
  using(var w=new BinaryWriter(File.Create(output))){w.Write(found?1:0);w.Write(found?2:records.Count);if(found){Write(w,w1,records[w1]);Write(w,w2,records[w2]);}else foreach(var p in records)Write(w,p.Key,p.Value);}
  File.WriteAllText(output+".status.json",System.Text.Json.JsonSerializer.Serialize(new {found,states=records.Count,tuples,seconds=watch.Elapsed.TotalSeconds,bound,names=Names,costs=Costs}));
 }
}
