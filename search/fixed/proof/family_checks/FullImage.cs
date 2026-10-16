using System;
using System.IO;
using System.Collections.Generic;
public static class FullImage {
 // UInt64.GetHashCode folds equal 32-bit truth-table halves to zero.
 // Thousands of <=5-variable functions collide under that default hash.
 sealed class TruthHash : IEqualityComparer<ulong> {
  public bool Equals(ulong a,ulong b)=>a==b;
  public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return (int)(x^(x>>32));}}
 }
 struct Rec { public int T,G,A,B,C,E; public Rec(int t,int g,int a,int b=-1,int c=-1,int e=-1){T=t;G=g;A=a;B=b;C=c;E=e;} }
 static readonly string[] Names={"INV","BUF","NAND2","NOR2","AND2","OR2","XOR2","XNOR2","NAND3","OAI21","AOI21","NOR3","AND3","OR3","MUX2","OAI22","AOI22","NAND4","NOR4","AND4","OR4"};
 static readonly int[] Costs={22048,33557,27886,40650,40171,56414,73019,57604,34767,32651,51619,61543,51869,85840,75175,54596,57255,44487,91313,65492,118592};
 public static ulong Eval(int g,ulong a,ulong b,ulong c,ulong e) => g switch {
 0=>~a,1=>a,2=>~(a&b),3=>~(a|b),4=>a&b,5=>a|b,6=>a^b,7=>~(a^b),8=>~(a&b&c),9=>~((a|b)&c),10=>~((a&b)|c),11=>~(a|b|c),12=>a&b&c,13=>a|b|c,14=>(a&~c)|(b&c),15=>~((a|b)&(c|e)),16=>~((a&b)|(c&e)),17=>~(a&b&c&e),18=>~(a|b|c|e),19=>a&b&c&e,20=>a|b|c|e,_=>throw new Exception()};
 public static void Run(string input,string output,int bound,ulong target) {
  int n;ulong[] fs;int[] ts;
  using(var r=new BinaryReader(File.OpenRead(input))){n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();}}
  var records=new Dictionary<ulong,Rec>(new TruthHash());for(int i=0;i<n;i++)if(ts[i]<=bound)records[fs[i]]=new Rec(ts[i],-1,i);
  var watch=System.Diagnostics.Stopwatch.StartNew();long tuples=0;bool found=false;ulong w1=0,w2=0;
  void Add(int g,int a,int b=-1,int c=-1,int e=-1){
   ulong f=Eval(g,fs[a],b<0?0:fs[b],c<0?0:fs[c],e<0?0:fs[e]);int t=ts[a];if(b>=0)t=Math.Max(t,ts[b]);if(c>=0)t=Math.Max(t,ts[c]);if(e>=0)t=Math.Max(t,ts[e]);t+=Costs[g];tuples++;
   if(!records.TryGetValue(f,out var old)||t<old.T){records[f]=new Rec(t,g,a,b,c,e);}
  }
  for(int g=0;g<Names.Length&&!found;g++){
   var ids=new List<int>();for(int i=0;i<n;i++)if(ts[i]+Costs[g]<=bound)ids.Add(i);int m=ids.Count;
   if(g<=1){for(int a=0;a<m&&!found;a++)Add(g,ids[a]);}
   else if(g<=7){for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)Add(g,ids[a],ids[b]);}
   else if(g==9||g==10){for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)for(int c=0;c<m;c++)Add(g,ids[a],ids[b],ids[c]);}
   else if(g==14){for(int a=0;a<m&&!found;a++)for(int b=0;b<m;b++)for(int c=0;c<m;c++)Add(g,ids[a],ids[b],ids[c]);}
   else if(g<15){for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)for(int c=b;c<m;c++)Add(g,ids[a],ids[b],ids[c]);}
   else if(g==15||g==16){for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)for(int c=a;c<m;c++)for(int e=(c==a?b:c);e<m;e++)Add(g,ids[a],ids[b],ids[c],ids[e]);}
   else{for(int a=0;a<m&&!found;a++)for(int b=a;b<m;b++)for(int c=b;c<m;c++)for(int e=c;e<m;e++)Add(g,ids[a],ids[b],ids[c],ids[e]);}
   string progress=$"{Names[g]} inputs={m} states={records.Count} tuples={tuples} seconds={watch.Elapsed.TotalSeconds:F2} found={found}";
   Console.WriteLine(progress);File.AppendAllText(output+".progress.log",progress+Environment.NewLine);
  }
  void Write(BinaryWriter w,ulong f,Rec q){w.Write(f);w.Write(q.T);w.Write(q.G);w.Write(q.A);w.Write(q.B);w.Write(q.C);w.Write(q.E);}
  using(var w=new BinaryWriter(File.Create(output))){w.Write(found?1:0);w.Write(found?2:records.Count);if(found){Write(w,w1,records[w1]);Write(w,w2,records[w2]);}else foreach(var p in records)Write(w,p.Key,p.Value);}
  File.WriteAllText(output+".status.json",System.Text.Json.JsonSerializer.Serialize(new {found,states=records.Count,tuples,seconds=watch.Elapsed.TotalSeconds,bound,names=Names,costs=Costs}));
 }
}
