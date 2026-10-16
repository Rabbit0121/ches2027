using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
public static class OaiEngine {
 struct Hit { public int T,A,B,C; public Hit(int t,int a,int b,int c){T=t;A=a;B=b;C=c;} }
 static List<ulong> Maxima(IEnumerable<ulong> keys) {
  var all=new List<ulong>(keys); all.Sort((a,b)=>{int c=BitOperations.PopCount(b).CompareTo(BitOperations.PopCount(a));return c!=0?c:a.CompareTo(b);});
  var kept=new List<ulong>();var posts=new List<ulong>[64];for(int i=0;i<64;i++)posts[i]=new List<ulong>();
  foreach(ulong z in all) {
   bool dominated=false;
   if(z==0)dominated=kept.Count>0;
   else for(int w=0;w<(kept.Count+63)/64;w++) {
    ulong possible=ulong.MaxValue, q=z;
    while(q!=0&&possible!=0){int b=BitOperations.TrailingZeroCount(q);q&=q-1;possible&=posts[b][w];}
    if(possible!=0){dominated=true;break;}
   }
   if(dominated)continue;
   int ix=kept.Count;kept.Add(z);
   if((ix&63)==0)for(int b=0;b<64;b++)posts[b].Add(0);
   ulong v=z;while(v!=0){int b=BitOperations.TrailingZeroCount(v);v&=v-1;posts[b][ix>>6]|=1UL<<(ix&63);}
  }
  return kept;
 }
 public static void Run(string input,string output,ulong target) {
  var watch=System.Diagnostics.Stopwatch.StartNew();int n;ulong[] fs;int[] ts;
  using(var r=new BinaryReader(File.OpenRead(input))){n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();}}
  ulong forbidden=~target;int words=(n+63)/64;var posts=new ulong[64][];
  for(int b=0;b<64;b++)if(((forbidden>>b)&1)!=0)posts[b]=new ulong[words];
  for(int i=0;i<n;i++){ulong z=forbidden&~fs[i];while(z!=0){int b=BitOperations.TrailingZeroCount(z);posts[b][i>>6]|=1UL<<(i&63);z&=z-1;}}
  var image=new Dictionary<ulong,Hit>();long compatible=0,pairs=0;
  for(int c=0;c<n;c++) {
   ulong cz=fs[c]&forbidden,cy=fs[c]&target;if(cy==0)continue;
   var bits=new int[BitOperations.PopCount(cz)];int k=0;while(cz!=0){bits[k++]=BitOperations.TrailingZeroCount(cz);cz&=cz-1;}
   var projections=new Dictionary<ulong,int>();
   for(int w=0;w<words;w++) {
    ulong choices=ulong.MaxValue;foreach(int bit in bits){choices&=posts[bit][w];if(choices==0)break;}
    while(choices!=0){int a=(w<<6)+BitOperations.TrailingZeroCount(choices);choices&=choices-1;if(a>=n)continue;
     compatible++;ulong z=fs[a]&cy;if(z==0)continue;
     if(!projections.TryGetValue(z,out int old)||ts[a]<ts[old])projections[z]=a;
    }
   }
   var masks=Maxima(projections.Keys);
   for(int i=0;i<masks.Count;i++)for(int j=i;j<masks.Count;j++) {
    ulong cover=masks[i]|masks[j];int a=projections[masks[i]],b=projections[masks[j]],t=Math.Max(ts[c],Math.Max(ts[a],ts[b]))+32651;pairs++;
    if(!image.TryGetValue(cover,out Hit h)||t<h.T)image[cover]=new Hit(t,a,b,c);
   }
   if(c%1000==0)Console.WriteLine($"c={c}/{n} compatible={compatible} pairs={pairs} image={image.Count} elapsed={watch.Elapsed.TotalSeconds:F2}");
  }
  Console.WriteLine($"pairs_complete image={image.Count} compatible={compatible} pairs={pairs} elapsed={watch.Elapsed.TotalSeconds:F2}");
  var final=Maxima(image.Keys);
  using(var w=new BinaryWriter(File.Create(output))){w.Write(final.Count);foreach(ulong cover in final){Hit h=image[cover];w.Write(cover);w.Write(h.T);w.Write(h.A);w.Write(h.B);w.Write(h.C);}}
  Console.WriteLine($"complete retained={final.Count} elapsed={watch.Elapsed.TotalSeconds:F2}");
 }
}
