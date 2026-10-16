using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
public static class Nand3CenterProof {
 sealed class U64Hash:IEqualityComparer<ulong>{public bool Equals(ulong a,ulong b)=>a==b;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return (int)x;}}}
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
 public static void Run(string input,string output,ulong target,string knownPath) {
  var watch=System.Diagnostics.Stopwatch.StartNew();int n;ulong[] fs;int[] ts;
  using(var r=new BinaryReader(File.OpenRead(input))){n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();}}
  int nk;ulong[] known;using(var r=new BinaryReader(File.OpenRead(knownPath))){nk=r.ReadInt32();known=new ulong[nk];for(int i=0;i<nk;i++)known[i]=r.ReadUInt64();}
  int kw=(nk+63)/64;var kp=new ulong[64][];for(int bit=0;bit<64;bit++)kp[bit]=new ulong[kw];
  for(int i=0;i<nk;i++){ulong z=known[i];while(z!=0){int bit=BitOperations.TrailingZeroCount(z);z&=z-1;kp[bit][i>>6]|=1UL<<(i&63);}}
  var coveredCache=new Dictionary<ulong,bool>(new U64Hash());long pruned=0;
  bool Covered(ulong z){if(z==0)return true;if(coveredCache.TryGetValue(z,out bool answer))return answer;for(int w=0;w<kw;w++){ulong choices=ulong.MaxValue,v=z;while(v!=0&&choices!=0){int bit=BitOperations.TrailingZeroCount(v);v&=v-1;choices&=kp[bit][w];}if(choices!=0){if(coveredCache.Count<4000000)coveredCache[z]=true;return true;}}if(coveredCache.Count<4000000)coveredCache[z]=false;return false;}
  ulong forbidden=~target;int words=(n+63)/64;var posts=new ulong[64][];
  for(int b=0;b<64;b++)if(((forbidden>>b)&1)!=0)posts[b]=new ulong[words];
  for(int i=0;i<n;i++){ulong z=forbidden&~fs[i];while(z!=0){int b=BitOperations.TrailingZeroCount(z);posts[b][i>>6]|=1UL<<(i&63);z&=z-1;}}
  var image=new Dictionary<ulong,Hit>(new U64Hash());long compatible=0,pairs=0;
  int limit=n;
  for(int c=0;c<limit;c++) {
   if(Covered(fs[c]&target)){pruned++;continue;}
   var projections=new Dictionary<ulong,int>(new U64Hash());
   for(int a=c;a<n;a++) {
    ulong p=fs[a]&fs[c];if(Covered(p&target)){pruned++;continue;}
    ulong key=p^forbidden;
    if(!projections.TryGetValue(key,out int old)||ts[a]<ts[old])projections[key]=a;
   }
   var masks=Maxima(projections.Keys);
   int nw=(masks.Count+63)/64;var zs=new ulong[64][];for(int bit=0;bit<64;bit++)if(((forbidden>>bit)&1)!=0)zs[bit]=new ulong[nw];
   for(int i=0;i<masks.Count;i++){ulong v=forbidden&masks[i];while(v!=0){int bit=BitOperations.TrailingZeroCount(v);zs[bit][i>>6]|=1UL<<(i&63);v&=v-1;}}
   for(int i=0;i<masks.Count;i++){
    ulong pi=masks[i]^forbidden,req=pi&forbidden;var bits=new List<int>();while(req!=0){bits.Add(BitOperations.TrailingZeroCount(req));req&=req-1;}
    for(int w=i>>6;w<nw;w++){
     ulong available=ulong.MaxValue;foreach(int bit in bits){available&=zs[bit][w];if(available==0)break;}if(w==(i>>6))available&=ulong.MaxValue<<(i&63);
     while(available!=0){int j=(w<<6)+BitOperations.TrailingZeroCount(available);available&=available-1;if(j>=masks.Count)continue;pairs++;ulong cover=pi&(masks[j]^forbidden);if(Covered(cover)){pruned++;continue;}
      int a=projections[masks[i]],b=projections[masks[j]],t=Math.Max(ts[c],Math.Max(ts[a],ts[b]))+34767;compatible++;
      if(!image.TryGetValue(cover,out Hit h)||t<h.T)image[cover]=new Hit(t,a,b,c);
     }
    }
   }
   if(c%500==0){using(var cp=new BinaryWriter(File.Create(output+".checkpoint"))){cp.Write(image.Count);foreach(var kv in image){cp.Write(kv.Key);cp.Write(kv.Value.T);cp.Write(kv.Value.A);cp.Write(kv.Value.B);cp.Write(kv.Value.C);}}File.WriteAllText(output+".progress.json",$"{{\"status\":\"PARTIAL\",\"centers\":{c},\"total\":{n},\"new_covers\":{image.Count},\"pruned\":{pruned},\"seconds\":{watch.Elapsed.TotalSeconds}}}");}if(c%100==0)Console.WriteLine($"c={c}/{n} compatible={compatible} pairs={pairs} image={image.Count} elapsed={watch.Elapsed.TotalSeconds:F2}");
  }
  Console.WriteLine($"pairs_complete image={image.Count} compatible={compatible} pairs={pairs} elapsed={watch.Elapsed.TotalSeconds:F2}");
  var final=Maxima(image.Keys);
  using(var w=new BinaryWriter(File.Create(output))){w.Write(final.Count);foreach(ulong cover in final){Hit h=image[cover];w.Write(cover);w.Write(h.T);w.Write(h.A);w.Write(h.B);w.Write(h.C);}}
  File.WriteAllText(output+".status.json",$"{{\"status\":\"COMPLETE_UNION_COVERAGE_BASIS\",\"inputs\":{n},\"known_covers\":{nk},\"new_covers\":{final.Count},\"pairs\":{pairs},\"pruned\":{pruned},\"cache_queries\":{coveredCache.Count},\"seconds\":{watch.Elapsed.TotalSeconds}}}");Console.WriteLine($"complete retained={final.Count} elapsed={watch.Elapsed.TotalSeconds:F2}");
 }
}
