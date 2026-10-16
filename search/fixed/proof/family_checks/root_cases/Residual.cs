using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
public static class Residual {
 sealed class Hash:IEqualityComparer<ulong>{public bool Equals(ulong x,ulong y)=>x==y;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return(int)x;}}}
 public static void Run(string image,string pairs,string output,ulong target){RunVirtual(image,pairs,output,target,false);}
 public static void RunVirtual(string image,string pairs,string output,ulong target,bool invert){
  var sw=System.Diagnostics.Stopwatch.StartNew();int n;ulong[] fs;int[] ts;
  using(var r=new BinaryReader(File.OpenRead(image))){r.ReadInt32();n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();if(invert)fs[i]=~fs[i];ts[i]=r.ReadInt32();r.BaseStream.Position+=20;}}
  ulong goal=~target;int words=(n+63)/64;var one=new ulong[64][];var counts=new int[64];var order=new List<int>();
  for(int b=0;b<64;b++)if(((goal>>b)&1)!=0){one[b]=new ulong[words];order.Add(b);}
  for(int i=0;i<n;i++){ulong z=fs[i]&goal;while(z!=0){int b=BitOperations.TrailingZeroCount(z);one[b][i>>6]|=1UL<<(i&63);counts[b]++;z&=z-1;}}
  order.Sort((a,b)=>counts[a].CompareTo(counts[b]));
  var covers=new List<(ulong f,int a,int b)>();
  using(var r=new BinaryReader(File.OpenRead(pairs))){int m=r.ReadInt32();for(int i=0;i<m;i++){ulong f=r.ReadUInt64();r.ReadInt32();int a=r.ReadInt32(),b=r.ReadInt32();covers.Add((f,a,b));}}
  covers.Sort((a,b)=>BitOperations.PopCount(b.f).CompareTo(BitOperations.PopCount(a.f)));
  long filtered=0,projections=0;int tested=0;var need=new int[64];
  foreach(var cv in covers){
   ulong residual=goal&~cv.f;int used=0;foreach(int b in order)if(((residual>>b)&1)!=0)need[used++]=b;
   var unique=new Dictionary<ulong,int>(new Hash());
   for(int w=0;w<words;w++){
    ulong possible=ulong.MaxValue;for(int k=0;k<used&&possible!=0;k++)possible&=one[need[k]][w];
    while(possible!=0){int ix=(w<<6)+BitOperations.TrailingZeroCount(possible);possible&=possible-1;if(ix>=n)continue;filtered++;ulong p=fs[ix]&target;if(!unique.TryGetValue(p,out int oi)||ts[ix]<ts[oi])unique[p]=ix;}
   }
   var masks=new List<ulong>(unique.Keys);masks.Sort((a,b)=>BitOperations.PopCount(a).CompareTo(BitOperations.PopCount(b)));projections+=masks.Count;
   int m=masks.Count,pwords=(m+63)/64;var zero=new ulong[64][];var ones=new List<int>();
   for(int b=0;b<64;b++)if(((target>>b)&1)!=0){zero[b]=new ulong[pwords];ones.Add(b);}
   for(int i=0;i<m;i++){ulong z=target&~masks[i];while(z!=0){int b=BitOperations.TrailingZeroCount(z);zero[b][i>>6]|=1UL<<(i&63);z&=z-1;}}
   for(int i=0;i<m;i++){
    int nb=0;foreach(int b in ones)if(((masks[i]>>b)&1)!=0)need[nb++]=b;
    for(int w=i>>6;w<pwords;w++){
     ulong possible=ulong.MaxValue;for(int k=0;k<nb&&possible!=0;k++)possible&=zero[need[k]][w];if(w==(i>>6))possible&=ulong.MaxValue<<(i&63);
     if(w==pwords-1&&(m&63)!=0)possible&=(1UL<<(m&63))-1;
     if(possible!=0){int j=(w<<6)+BitOperations.TrailingZeroCount(possible);int a=unique[masks[i]],b=unique[masks[j]];if((fs[a]&fs[b]&target)!=0||((fs[a]&fs[b])|cv.f)!=goal)throw new Exception("bad witness");File.WriteAllText(output,$"{{\"status\":\"SAT\",\"old_indices\":[{cv.a},{cv.b}],\"image_indices\":[{a},{b}],\"tested\":{tested},\"seconds\":{sw.Elapsed.TotalSeconds}}}");return;}
    }
   }
   tested++;if(tested%50==0){Console.WriteLine($"residuals={tested}/{covers.Count} filtered={filtered} projected={projections} current={m} seconds={sw.Elapsed.TotalSeconds:F2}");File.WriteAllText(output+".progress",$"{{\"status\":\"RUNNING\",\"tested\":{tested},\"total\":{covers.Count},\"seconds\":{sw.Elapsed.TotalSeconds}}}");}
  }
  File.WriteAllText(output,$"{{\"status\":\"NO_SECOND_PAIR_COMPLETES_ANY_GIVEN_COVER\",\"tested\":{tested},\"image_functions\":{n},\"filtered\":{filtered},\"projected\":{projections},\"seconds\":{sw.Elapsed.TotalSeconds}}}");
 }
}
