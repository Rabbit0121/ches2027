using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
public static class Aoi21Stream {
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

 sealed class CareSet {
  public HashSet<ulong> Keys=new HashSet<ulong>(new TruthHash());
  public List<Rec> Witnesses=new List<Rec>();
  public List<ulong>[] Zero=new List<ulong>[64];
  public CareSet(ulong y){for(int b=0;b<64;b++)if(((y>>b)&1)!=0)Zero[b]=new List<ulong>();}
  public bool QueryAdd(ulong p,Rec rec,ulong y,out Rec other) {
   other=rec;if(p==0)return true;if(Keys.Contains(p))return false;
   for(int w=0;w<(Witnesses.Count+63)/64;w++) {
    ulong q=p,possible=ulong.MaxValue;
    while(q!=0&&possible!=0){int b=BitOperations.TrailingZeroCount(q);q&=q-1;possible&=Zero[b][w];}
    if(possible!=0){int j=(w<<6)+BitOperations.TrailingZeroCount(possible);other=Witnesses[j];return true;}
   }
   int ix=Witnesses.Count;Keys.Add(p);Witnesses.Add(rec);
   if((ix&63)==0)for(int b=0;b<64;b++)if(Zero[b]!=null)Zero[b].Add(0);
   ulong v=y&~p;while(v!=0){int b=BitOperations.TrailingZeroCount(v);v&=v-1;Zero[b][ix>>6]|=1UL<<(ix&63);}
   return false;
  }
 }
 public static void Run(string input,string centers,string output,int bound,ulong target,double secondsLimit,int statesLimit) {
  int n;ulong[] fs;int[] ts;
  using(var r=new BinaryReader(File.OpenRead(input))){n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();}}
  var rs=new List<ulong>();var cr=new List<Rec>();ulong ztarget=~target;int minCount=64;
  using(var r=new BinaryReader(File.OpenRead(centers))){int nc=r.ReadInt32();for(int i=0;i<nc;i++){ulong cf=r.ReadUInt64();int t=r.ReadInt32(),g=r.ReadInt32(),a=r.ReadInt32(),b=r.ReadInt32(),c=r.ReadInt32(),e=r.ReadInt32();if((cf&target)!=0)throw new Exception("bad c");ulong rr=ztarget&~cf;rs.Add(rr);cr.Add(new Rec(t,g,a,b,c,e));minCount=Math.Min(minCount,BitOperations.PopCount(rr));}}
  int nr=rs.Count,nrw=(nr+63)/64;var need=new ulong[64][];ulong active=0;
  for(int b=0;b<64;b++)need[b]=new ulong[nrw];
  for(int i=0;i<nr;i++){ulong r=rs[i];active|=r;while(r!=0){int b=BitOperations.TrailingZeroCount(r);r&=r-1;need[b][i>>6]|=1UL<<(i&63);}}
  var care=new CareSet[nr];for(int i=0;i<nr;i++)care[i]=new CareSet(target);
  var seen=new HashSet<ulong>(new TruthHash());int totalStates=0,witnessCenter=-1;Rec wa=default,wb=default;long tuples=0,eligibleEvents=0;bool found=false;string status="COMPLETE_NO_AOI21_AT_BOUND";
  var watch=System.Diagnostics.Stopwatch.StartNew();
  void Process(ulong f,Rec q) {
   if(found||BitOperations.PopCount(f&ztarget)<minCount||seen.Contains(f))return;
   ulong missing=active&~f,projection=f&target;bool any=false;
   for(int w=0;w<nrw;w++) {
    ulong bset=missing,possible=ulong.MaxValue;
    while(bset!=0&&possible!=0){int bit=BitOperations.TrailingZeroCount(bset);bset&=bset-1;possible&=~need[bit][w];}
    while(possible!=0){int i=(w<<6)+BitOperations.TrailingZeroCount(possible);possible&=possible-1;if(i>=nr)continue;eligibleEvents++;any=true;
     int old=care[i].Witnesses.Count;
     if(care[i].QueryAdd(projection,q,target,out Rec other)){found=true;status="SAT";wa=q;wb=other;witnessCenter=i;return;}
     totalStates+=care[i].Witnesses.Count-old;
     if(totalStates>=statesLimit){found=true;status="UNKNOWN_STATE_LIMIT";return;}
    }
   }
   if(any&&seen.Count<500000)seen.Add(f);
  }
  for(int i=0;i<n&&!found;i++)if(ts[i]<=bound)Process(fs[i],new Rec(ts[i],-1,i));
  void Add(int g,int a,int b=-1,int c=-1,int e=-1){
   if(found)return;
   ulong f=Eval(g,fs[a],b<0?0:fs[b],c<0?0:fs[c],e<0?0:fs[e]);int t=ts[a];if(b>=0)t=Math.Max(t,ts[b]);if(c>=0)t=Math.Max(t,ts[c]);if(e>=0)t=Math.Max(t,ts[e]);t+=Costs[g];tuples++;
   if((tuples&65535)==0&&watch.Elapsed.TotalSeconds>=secondsLimit){found=true;status="UNKNOWN_TIME_LIMIT";return;}
   Process(f,new Rec(t,g,a,b,c,e));
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
   string progress=$"{Names[g]} inputs={m} states={totalStates} tuples={tuples} seconds={watch.Elapsed.TotalSeconds:F2} found={found}";
   Console.WriteLine(progress);File.AppendAllText(output+".progress.log",progress+Environment.NewLine);
  }

  using(var pw=new BinaryWriter(File.Create(output+".projections.bin"))) {
   pw.Write(nr);for(int i=0;i<nr;i++){pw.Write(rs[i]);pw.Write(care[i].Keys.Count);foreach(ulong p in care[i].Keys)pw.Write(p);}
  }
  int[] Pack(Rec r)=>new int[]{r.T,r.G,r.A,r.B,r.C,r.E};
  File.WriteAllText(output,System.Text.Json.JsonSerializer.Serialize(new {status,tuples,states=totalStates,eligibleEvents,seen=seen.Count,centers=nr,seconds=watch.Elapsed.TotalSeconds,bound,names=Names,costs=Costs,witnessCenter,first=Pack(wa),second=Pack(wb),center=witnessCenter<0?null:Pack(cr[witnessCenter])}));
 }
}
