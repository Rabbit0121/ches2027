using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
public static class GlobalCross {
 sealed class Hash:IEqualityComparer<ulong>{public bool Equals(ulong x,ulong y)=>x==y;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return(int)x;}}}
 struct Node { public ulong AndY,OrZ;public int L,R,Start,End,Groups; }
 static Node[] tree;static int nodes;static ulong[] fs,ys;static int[] ids,ts,groups;static ulong Y,Z;static int threshold;static HashSet<ulong> allowed;static bool useOr,full;static long visits,pairs;static Dictionary<ulong,(int,int,int)> found;
 static int Build(int lo,int hi){
  int ix=nodes++;Node v=new Node{Start=lo,End=hi,L=-1,R=-1};
  if(ys[lo]==ys[hi-1]){v.AndY=ys[lo];for(int i=lo;i<hi;i++){v.OrZ|=fs[i]&Z;v.Groups|=groups[i];}}
  else {int bit=63-BitOperations.LeadingZeroCount(ys[lo]^ys[hi-1]);ulong boundary=(ys[lo]&(~0UL<<bit))|(1UL<<bit);int a=lo,b=hi;while(a<b){int m=(a+b)>>1;if(ys[m]<boundary)a=m+1;else b=m;}if(a<=lo||a>=hi)throw new Exception("split");v.L=Build(lo,a);v.R=Build(a,hi);v.AndY=tree[v.L].AndY&tree[v.R].AndY;v.OrZ=tree[v.L].OrZ|tree[v.R].OrZ;v.Groups=tree[v.L].Groups|tree[v.R].Groups;}
  tree[ix]=v;return ix;
 }
 static System.Diagnostics.Stopwatch clock;static int seconds;static bool limited;
 static void Join(int ai,int bi){
  if(limited)return;visits++;if(visits%10000000==0){Console.WriteLine($"join visits={visits} leafpairs={pairs} covers={found.Count} seconds={clock.Elapsed.TotalSeconds:F2}");if(seconds>0&&clock.Elapsed.TotalSeconds>seconds){limited=true;return;}}
  ref Node a=ref tree[ai];ref Node b=ref tree[bi];if((a.Groups|b.Groups)!=3||!allowed.Contains(useOr?(a.AndY|b.AndY):(a.AndY&b.AndY))||BitOperations.PopCount(useOr?(a.OrZ|b.OrZ):(a.OrZ&b.OrZ))<threshold)return;
  if(ai==bi&&a.L>=0){Join(a.L,a.L);Join(a.L,a.R);Join(a.R,a.R);return;}
  if(a.L<0&&b.L<0){for(int i=a.Start;i<a.End;i++)for(int j=ai==bi?i:b.Start;j<b.End;j++){if(groups[i]==groups[j])continue;pairs++;ulong value=useOr?(fs[i]|fs[j]):(fs[i]&fs[j]);ulong cover=full?value:(value&Z);if(BitOperations.PopCount(value&Z)>=threshold&&!found.ContainsKey(cover))found.Add(cover,(ids[i],ids[j],Math.Max(ts[i],ts[j])));}return;}
  if(a.L>=0&&(b.L<0||a.End-a.Start>=b.End-b.Start)){Join(a.L,bi);Join(a.R,bi);}else{Join(ai,b.L);Join(ai,b.R);}
 }
 public static void Run(string centers,string image,string output,ulong target,bool combineOr,bool keepFull){
  useOr=combineOr;full=keepFull;allowed=new HashSet<ulong>(new Hash());using(var r=new BinaryReader(File.OpenRead(centers))){int n=r.ReadInt32();for(int i=0;i<n;i++){ulong s=r.ReadUInt64(),q=s;while(true){allowed.Add(q);if(q==0)break;q=(q-1)&s;}}}int minimum=1,limit=0;bool invert=false;
  var sw=System.Diagnostics.Stopwatch.StartNew();Y=target;Z=~Y;threshold=minimum;visits=pairs=0;nodes=0;found=new Dictionary<ulong,(int,int,int)>(new Hash());var vf=new List<ulong>();var vi=new List<int>();var vt=new List<int>();var vg=new List<int>();
  using(var r=new BinaryReader(File.OpenRead(image))){r.ReadInt32();int n=r.ReadInt32();for(int i=0;i<n;i++){ulong f=r.ReadUInt64();if(invert)f=~f;int t=r.ReadInt32();int group=r.ReadInt32()==-2?2:1;r.BaseStream.Position+=16;if(BitOperations.PopCount(f&Z)>=threshold){vf.Add(f);vi.Add(i);vt.Add(t);vg.Add(group);}}}
  int count=vf.Count;ys=new ulong[count];ids=vi.ToArray();fs=vf.ToArray();ts=vt.ToArray();groups=vg.ToArray();var perm=new int[count];for(int i=0;i<count;i++){ys[i]=fs[i]&Y;perm[i]=i;}Array.Sort(ys,perm);var nf=new ulong[count];var ni=new int[count];var nt=new int[count];var ng=new int[count];for(int i=0;i<count;i++){nf[i]=fs[perm[i]];ni[i]=ids[perm[i]];nt[i]=ts[perm[i]];ng[i]=groups[perm[i]];}fs=nf;ids=ni;ts=nt;groups=ng;tree=new Node[2*count];if(count>0)Build(0,count);Console.WriteLine($"built inputs={count} nodes={nodes} seconds={sw.Elapsed.TotalSeconds:F2}");
  clock=sw;seconds=limit;limited=false;if(count>0)Join(0,0);int end=limited?0:count;
  using(var w=new BinaryWriter(File.Create(output))){w.Write(found.Count);foreach(var kv in found){w.Write(kv.Key);w.Write(kv.Value.Item3);w.Write(kv.Value.Item1);w.Write(kv.Value.Item2);}}
  File.WriteAllText(output+".json",$"{{\"status\":\"{(end==count?"COMPLETE_CENTER_COMPATIBLE_CROSS_PAIRS":"PARTIAL_SAFE_LARGE_AND_PAIRS")}\",\"threshold\":{threshold},\"inputs\":{count},\"tested\":{end},\"covers\":{found.Count},\"visits\":{visits},\"leafpairs\":{pairs},\"seconds\":{sw.Elapsed.TotalSeconds}}}");
 }
}
