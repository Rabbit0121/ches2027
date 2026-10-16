using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
using System.Threading.Tasks;
public static class MixedMaxFast {
 sealed class Hash:IEqualityComparer<ulong>{public bool Equals(ulong x,ulong y)=>x==y;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return(int)x;}}}
 struct Node{public ulong Or,And;public int L,R,Bit,Pop,Id;}
 static Node[] tree;static ulong[] keys;static int nn;
 static readonly ParallelOptions Parallelism=new ParallelOptions{MaxDegreeOfParallelism=4};
 static int Build(int lo,int hi){int id=nn++;Node n=new Node{L=-1,R=-1};if(hi-lo==1){n.Or=n.And=keys[lo];n.Pop=BitOperations.PopCount(keys[lo]);n.Id=lo;}else{n.Bit=63-BitOperations.LeadingZeroCount(keys[lo]^keys[hi-1]);ulong edge=(keys[lo]&(~0UL<<n.Bit))|(1UL<<n.Bit);int a=lo,b=hi;while(a<b){int m=(a+b)>>1;if(keys[m]<edge)a=m+1;else b=m;}n.L=Build(lo,a);n.R=Build(a,hi);Node x=tree[n.L],y=tree[n.R];n.Or=x.Or|y.Or;n.And=x.And&y.And;n.Pop=Math.Max(x.Pop,y.Pop);n.Id=x.Pop>=y.Pop?x.Id:y.Id;}tree[id]=n;return id;}
 static int Super(int at,ulong f,int minimumPop){ref Node n=ref tree[at];if(n.Pop<minimumPop||(n.Or&f)!=f)return -1;if((n.And&f)==f)return n.Id;if(n.L<0)return -1;if(((f>>n.Bit)&1)!=0)return Super(n.R,f,minimumPop);int r=Super(n.R,f,minimumPop);return r>=0?r:Super(n.L,f,minimumPop);}
 static void Init(ulong[] a){keys=a;nn=0;tree=new Node[Math.Max(1,a.Length*2)];if(a.Length>0)Build(0,a.Length);}
 // Manifest lines: sourceId TAB absolutePath TAB headerBytes TAB strideBytes TAB countOffset.
 static IEnumerable<(int id,string path,int header,int stride,int offset)> Specs(string path){foreach(string line in File.ReadAllLines(path)){if(line.Trim().Length==0)continue;string[] p=line.Split('\t');yield return(int.Parse(p[0]),p[1],int.Parse(p[2]),int.Parse(p[3]),int.Parse(p[4]));}}
 static int Count(BinaryReader r,int header,int stride,int offset){r.BaseStream.Position=offset;int n=r.ReadInt32();if(n<0||r.BaseStream.Length!=header+(long)n*stride)throw new Exception("bad binary dimensions");r.BaseStream.Position=header;return n;}
 public static void Run(string manifest,string previous,string output,ulong xorMask){var sw=System.Diagnostics.Stopwatch.StartNew();var map=new Dictionary<ulong,long>(new Hash());long records=0;
  if(previous.Length>0){using(var r=new BinaryReader(File.OpenRead(previous))){int n=Count(r,4,16,0);for(int i=0;i<n;i++){ulong f=r.ReadUInt64();int s=r.ReadInt32(),row=r.ReadInt32();map.TryAdd(f^xorMask,((long)s<<32)|(uint)row);records++;}}}
  foreach(var spec in Specs(manifest)){using(var r=new BinaryReader(File.OpenRead(spec.path))){int n=Count(r,spec.header,spec.stride,spec.offset);for(int i=0;i<n;i++){ulong f=r.ReadUInt64();for(int skip=8;skip<spec.stride;skip+=4)r.ReadInt32();map.TryAdd(f^xorMask,((long)spec.id<<32)|(uint)i);}records+=n;Console.WriteLine($"read source={spec.id} count={n} unique={map.Count} seconds={sw.Elapsed.TotalSeconds:F3}");}}
  var a=new ulong[map.Count];map.Keys.CopyTo(a,0);var groups=new List<ulong>[65];for(int i=0;i<65;i++)groups[i]=new List<ulong>();foreach(ulong k in a)groups[BitOperations.PopCount(k)].Add(k);var kept=new List<ulong>();long tested=0;for(int pop=64;pop>=0;pop--){if(groups[pop].Count==0)continue;var prior=kept.ToArray();Array.Sort(prior);Init(prior);var group=groups[pop];var retain=new bool[group.Count];int minimum=pop+1;
   // All queries see the same immutable higher-popcount tree. Append only
   // after the batch completes, in the original order, for identical output.
   Parallel.For(0,group.Count,Parallelism,i=>retain[i]=prior.Length==0||Super(0,group[i],minimum)<0);
   for(int i=0;i<group.Count;i++)if(retain[i])kept.Add(group[i]);
   tested+=group.Count;Console.WriteLine($"pop={pop} tested={tested}/{a.Length} kept={kept.Count} seconds={sw.Elapsed.TotalSeconds:F3}");}kept.Sort();
  using(var w=new BinaryWriter(File.Create(output))){w.Write(kept.Count);foreach(ulong k in kept){long origin=map[k];w.Write(k^xorMask);w.Write((int)(origin>>32));w.Write((int)origin);}}
  using(var w=new BinaryWriter(File.Create(output+".truths"))){w.Write(kept.Count);foreach(ulong k in kept)w.Write(k^xorMask);}
  File.WriteAllText(output+".json",$"{{\"status\":\"COMPLETE_EXACT_MIXED_MAXIMA\",\"source_rows\":{records},\"unique_functions\":{a.Length},\"maximal_functions\":{kept.Count},\"xor_mask\":{xorMask},\"seconds\":{sw.Elapsed.TotalSeconds}}}");Console.WriteLine(File.ReadAllText(output+".json"));
 }
 public static void Verify(string manifest,string maxima,string output,ulong xorMask){var sw=System.Diagnostics.Stopwatch.StartNew();var actual=new List<ulong>();using(var r=new BinaryReader(File.OpenRead(maxima))){int n=Count(r,4,16,0);for(int i=0;i<n;i++){actual.Add(r.ReadUInt64());r.ReadInt64();}}var order=new int[actual.Count];for(int i=0;i<order.Length;i++)order[i]=i;Array.Sort(order,(a,b)=>(actual[a]^xorMask).CompareTo(actual[b]^xorMask));var akeys=new ulong[order.Length];for(int i=0;i<order.Length;i++)akeys[i]=actual[order[i]]^xorMask;Init(akeys);long total=0;Directory.CreateDirectory(output);
  foreach(var spec in Specs(manifest)){using(var r=new BinaryReader(File.OpenRead(spec.path)))using(var w=new BinaryWriter(File.Create(Path.Combine(output,$"source{spec.id}.witness.bin")))){int n=Count(r,spec.header,spec.stride,spec.offset);w.Write(n);
   const int Block=65536;var queries=new ulong[Block];var answers=new int[Block];
   for(int begin=0;begin<n;begin+=Block){int count=Math.Min(Block,n-begin);
    for(int i=0;i<count;i++){queries[i]=r.ReadUInt64()^xorMask;for(int skip=8;skip<spec.stride;skip+=4)r.ReadInt32();}
    Parallel.For(0,count,Parallelism,i=>{ulong k=queries[i];int j=keys.Length==0?-1:Super(0,k,BitOperations.PopCount(k));if(j<0)throw new Exception($"uncovered source{spec.id} row{begin+i}");int idx=order[j];if(((actual[idx]^xorMask)&k)!=k)throw new Exception("bad direct witness");answers[i]=idx;});
    for(int i=0;i<count;i++)w.Write(answers[i]);
   }total+=n;Console.WriteLine($"verified source={spec.id} rows={n} seconds={sw.Elapsed.TotalSeconds:F3}");}}
  File.WriteAllText(Path.Combine(output,"native.json"),$"{{\"status\":\"ALL_SOURCE_ROWS_HAVE_EXPLICIT_DOMINATOR\",\"rows\":{total},\"maxima\":{actual.Count},\"seconds\":{sw.Elapsed.TotalSeconds}}}");
 }
}
