using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
using System.Text.Json;
public static class OaiFinalCover {
 sealed class Hash:IEqualityComparer<ulong>{public bool Equals(ulong a,ulong b)=>a==b;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return(int)x;}}}
 struct Row{public ulong F,Y;public int Id;}
 struct Node{public ulong MustY,MayZ;public int L,R,Start,End;}
 static Row[] rows;static Node[] tree;static int nodes;static ulong Y,Z;static HashSet<ulong> down;
 static ulong[] centers;static bool hit,limited;static int hitA,hitB;static long visits,pairs,prunedY,prunedZ;static double limit;
 static System.Diagnostics.Stopwatch watch;
 static int Build(int lo,int hi){
  if(nodes==tree.Length)Array.Resize(ref tree,checked(tree.Length*2));
  int at=nodes++;Node n=new Node{L=-1,R=-1,Start=lo,End=hi};
  bool sameY=rows[lo].Y==rows[hi-1].Y;
  if(sameY&&hi-lo<=16){n.MustY=rows[lo].Y;for(int i=lo;i<hi;i++)n.MayZ|=rows[i].F&Z;}
  else{
   // After separating Y groups, subdivide large groups by their actual Z
   // patterns as well. This makes the same safe MayZ pruning more selective.
   ulong first=sameY?rows[lo].F:rows[lo].Y,last=sameY?rows[hi-1].F:rows[hi-1].Y;
   int bit=63-BitOperations.LeadingZeroCount(first^last);ulong boundary=(first&(~0UL<<bit))|(1UL<<bit);
   int a=lo,b=hi;while(a<b){int m=(a+b)>>1;if((sameY?rows[m].F:rows[m].Y)<boundary)a=m+1;else b=m;}if(a<=lo||a>=hi)throw new Exception("bad tree split");
   n.L=Build(lo,a);n.R=Build(a,hi);n.MustY=tree[n.L].MustY&tree[n.R].MustY;n.MayZ=tree[n.L].MayZ|tree[n.R].MayZ;
  }
  tree[at]=n;return at;
 }
 static void Join(int ia,int ib){
  if(hit||limited)return;
  visits++;
  if(visits%10000000==0){Console.WriteLine($"visits={visits} pairs={pairs} seconds={watch.Elapsed.TotalSeconds:F2}");if(limit>0&&watch.Elapsed.TotalSeconds>limit){limited=true;return;}}
  ref Node a=ref tree[ia];ref Node b=ref tree[ib];
  // A lower bound on forbidden Y coverage must fit at least one real center.
  if(!down.Contains(a.MustY|b.MustY)){prunedY++;return;}
  // An upper bound on useful Z coverage must contain every target Z bit.
  if((a.MayZ|b.MayZ)!=Z){prunedZ++;return;}
  if(ia==ib&&a.L>=0){Join(a.L,a.L);Join(a.L,a.R);Join(a.R,a.R);return;}
  if(a.L<0&&b.L<0){
   // Each leaf has identical Y, so its downset test is exact.
   for(int i=a.Start;i<a.End;i++)for(int j=ia==ib?i:b.Start;j<b.End;j++){
    pairs++;ulong f=rows[i].F|rows[j].F;
    if((f&Z)==Z){if(!down.Contains(f&Y))throw new Exception("leaf incompatibility");hit=true;hitA=i;hitB=j;return;}
   }
   return;
  }
  if(a.L>=0&&(b.L<0||a.End-a.Start>=b.End-b.Start)){Join(a.L,ib);Join(a.R,ib);}else{Join(ia,b.L);Join(ia,b.R);}
 }
 public static void Run(string centerFile,string inputFile,string outputFile,ulong targetY,int limitSeconds){
  Y=targetY;Z=~Y;limit=limitSeconds;nodes=0;hit=limited=false;visits=pairs=prunedY=prunedZ=0;watch=System.Diagnostics.Stopwatch.StartNew();
  down=new HashSet<ulong>(new Hash());using(var r=new BinaryReader(File.OpenRead(centerFile))){int n=r.ReadInt32();centers=new ulong[n];for(int i=0;i<n;i++){ulong s=r.ReadUInt64();if((s&~Y)!=0)throw new Exception("invalid center zero mask");centers[i]=s;ulong sub=s;while(true){down.Add(sub);if(sub==0)break;sub=(sub-1)&s;}}if(r.BaseStream.Position!=r.BaseStream.Length)throw new Exception("center format");}
  using(var r=new BinaryReader(File.OpenRead(inputFile))){int n=r.ReadInt32();rows=new Row[n];for(int i=0;i<n;i++){ulong f=r.ReadUInt64();if(!down.Contains(f&Y))throw new Exception("input has no compatible center");rows[i]=new Row{F=f,Y=f&Y,Id=i};}if(r.BaseStream.Position!=r.BaseStream.Length)throw new Exception("input format");}
  int inputRecords=rows.Length;
  Array.Sort(rows,(a,b)=>a.Y!=b.Y?a.Y.CompareTo(b.Y):a.F.CompareTo(b.F));
  // Exact duplicates may arise from independently compressed blocks. Keep an
  // original source index; identical truth tables have identical query behavior.
  int unique=0;for(int i=0;i<rows.Length;i++)if(unique==0||rows[i].F!=rows[unique-1].F)rows[unique++]=rows[i];
  if(unique!=rows.Length)Array.Resize(ref rows,unique);
  int groups=0;for(int i=0;i<rows.Length;i++)if(i==0||rows[i].Y!=rows[i-1].Y)groups++;tree=new Node[Math.Max(1,2*groups+rows.Length/8)];if(rows.Length>0)Build(0,rows.Length);
  Console.WriteLine($"built functions={rows.Length} nodes={nodes} centers={centers.Length} downset={down.Count} seconds={watch.Elapsed.TotalSeconds:F2}");
  if(rows.Length>0)Join(0,0);
  int center=-1;ulong af=0,bf=0;int ai=-1,bi=-1;
  if(hit){af=rows[hitA].F;bf=rows[hitB].F;ai=rows[hitA].Id;bi=rows[hitB].Id;ulong need=(af|bf)&Y;for(int i=0;i<centers.Length;i++)if((need&~centers[i])==0){center=i;break;}if(center<0||((af|bf)&Z)!=Z)throw new Exception("bad final witness");}
  File.WriteAllText(outputFile,JsonSerializer.Serialize(new{status=hit?"SAT_COMMON_CENTER_TWO_COVER":limited?"PARTIAL":"COMPLETE_NO_COMMON_CENTER_TWO_COVER",input_records=inputRecords,inputs=rows.Length,centers=centers.Length,downset=down.Count,nodes,visits,pairs,prunedY,prunedZ,seconds=watch.Elapsed.TotalSeconds,Y,Z,input_a=ai,input_b=bi,truth_a=af,truth_b=bf,center_index=center,center_zero=center<0?0UL:centers[center]}));
 }
}
