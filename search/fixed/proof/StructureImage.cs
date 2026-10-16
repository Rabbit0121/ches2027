using System;
using System.IO;
using System.Collections.Generic;
using System.Text.Json;
public static class StructureImage {
 sealed class Hash:IEqualityComparer<ulong>{public bool Equals(ulong a,ulong b)=>a==b;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return(int)x;}}}
 struct Args {public int A,B,C,D;public Args(int a,int b=-1,int c=-1,int d=-1){A=a;B=b;C=c;D=d;}public int Get(int i)=>i==0?A:i==1?B:i==2?C:D;public Args Put(int i,int value){Args q=this;if(i==0)q.A=value;else if(i==1)q.B=value;else if(i==2)q.C=value;else q.D=value;return q;}}
 struct Rec{public int T,G;public Args Pins;public Rec(int t,int g,Args pins){T=t;G=g;Pins=pins;}}
 static readonly string[] Names={"INV","BUF","NAND2","NOR2","AND2","OR2","XOR2","XNOR2","NAND3","OAI21","AOI21","NOR3","AND3","OR3","MUX2","OAI22","AOI22","NAND4","NOR4","AND4","OR4"};
 static readonly int[] Costs={22048,33557,27886,40650,40171,56414,73019,57604,34767,32651,51619,61543,51869,85840,75175,54596,57255,44487,91313,65492,118592};
 static readonly int[] Arity={1,1,2,2,2,2,2,2,3,3,3,3,3,3,3,4,4,4,4,4,4};
 static ulong[] fs;static int[] ts;static Dictionary<ulong,int> lookup;static Dictionary<ulong,Rec> records;static long tuples;
 static ulong Eval(int g,Args q){ulong a=fs[q.A],b=q.B<0?0:fs[q.B],c=q.C<0?0:fs[q.C],d=q.D<0?0:fs[q.D];return g switch{0=>~a,1=>a,2=>~(a&b),3=>~(a|b),4=>a&b,5=>a|b,6=>a^b,7=>~(a^b),8=>~(a&b&c),9=>~((a|b)&c),10=>~((a&b)|c),11=>~(a|b|c),12=>a&b&c,13=>a|b|c,14=>(a&~c)|(b&c),15=>~((a|b)&(c|d)),16=>~((a&b)|(c&d)),17=>~(a&b&c&d),18=>~(a|b|c|d),19=>a&b&c&d,20=>a|b|c|d,_=>throw new Exception("gate")};}
 static ulong Op(ulong a,ulong b,int op)=>op==0?a&b:op==1?a|b:a^b;
 static Dictionary<ulong,Args> Fold(int[][] domains,int begin,int end,int op){
  var result=new Dictionary<ulong,Args>(new Hash());foreach(int i in domains[begin])result.TryAdd(fs[i],new Args(-1).Put(begin,i));
  for(int position=begin+1;position<end;position++){
   var next=new Dictionary<ulong,Args>(new Hash());foreach(var pair in result)foreach(int i in domains[position]){tuples++;next.TryAdd(Op(pair.Key,fs[i],op),pair.Value.Put(position,i));}result=next;
  }return result;
 }
 static void Emit(int gate,Args args,HashSet<int> domain,int fixedDelay){
  ulong f=Eval(gate,args);int t=0;for(int p=0;p<Arity[gate];p++)t=Math.Max(t,ts[args.Get(p)]);t+=Costs[gate];
  if(t>fixedDelay)throw new Exception("witness exceeds enumerated structure delay");
  if(!records.TryGetValue(f,out Rec old)||t<old.T)records[f]=new Rec(t,gate,args);
  if(domain!=null){if(!lookup.TryGetValue(f,out int i))throw new Exception("complete child image missing fixed-structure value");domain.Add(i);}
 }
 public static void Run(string input,string catalogue,string output,int bound,int childBound){
  var sw=System.Diagnostics.Stopwatch.StartNew();tuples=0;lookup=new Dictionary<ulong,int>(new Hash());records=new Dictionary<ulong,Rec>(new Hash());
  using(var r=new BinaryReader(File.OpenRead(input))){int n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();if(!lookup.TryGetValue(fs[i],out int old)||ts[i]<ts[old])lookup[fs[i]]=i;}if(r.BaseStream.Position!=r.BaseStream.Length)throw new Exception("input format");}
  foreach(var p in lookup)records[p.Key]=new Rec(ts[p.Value],-1,new Args(p.Value));
  using(var doc=JsonDocument.Parse(File.ReadAllText(catalogue))){
   var root=doc.RootElement;if(root.GetProperty("bound_fs").GetInt32()!=bound||root.GetProperty("truth_tables_evaluated").GetInt32()!=0)throw new Exception("catalogue scope");
   var nodes=root.GetProperty("nodes");int n=nodes.GetArrayLength();if(n!=root.GetProperty("structures").GetInt32())throw new Exception("structure count");
   int[][] cache=new int[n][];int[] delay=new int[n];int completed=0;
   foreach(var node in nodes.EnumerateArray()){int g=node.GetProperty("gate").GetInt32(),fixedDelay=node.GetProperty("delay").GetInt32();
    var children=node.GetProperty("children");int k=children.GetArrayLength();int[][] domains=new int[k][];int j=0,expected=Costs[g];
    if(k==0){if(g!=0&&g!=1)throw new Exception("paid leaf");var leaf=new int[6];for(int v=0;v<6;v++){ulong f=0;for(int x=0;x<64;x++)f|=((ulong)((x>>v)&1))<<x;if(g==0)f=~f;leaf[v]=lookup[f];}cache[completed]=leaf;}
    else{
     if(k!=Arity[g])throw new Exception("arity");int max=0;foreach(var c in children.EnumerateArray()){int id=c.GetInt32();if(id>=completed||cache[id]==null)throw new Exception("structure is not topological or child is over budget");domains[j++]=cache[id];max=Math.Max(max,delay[id]);}expected+=max;
     HashSet<int> result=fixedDelay<=childBound?new HashSet<int>():null;
     if(k==1){foreach(int a in domains[0]){tuples++;Emit(g,new Args(a),result,fixedDelay);}}
     else if(g==14){foreach(int a in domains[0])foreach(int b in domains[1])foreach(int c in domains[2]){tuples++;Emit(g,new Args(a,b,c),result,fixedDelay);}}
     else if(g==9||g==10||g==15||g==16){
      int inner=(g==10||g==16)?0:1;var left=Fold(domains,0,2,inner);var right=Fold(domains,2,k,inner);
      foreach(var a in left)foreach(var b in right){tuples++;Args q=a.Value.Put(2,b.Value.C);if(k==4)q=q.Put(3,b.Value.D);Emit(g,q,result,fixedDelay);}
     }else{
      int op=g==6||g==7?2:g==2||g==4||g==8||g==12||g==17||g==19?0:1;
      var partial=Fold(domains,0,k-1,op);foreach(var a in partial)foreach(int b in domains[k-1]){tuples++;Emit(g,a.Value.Put(k-1,b),result,fixedDelay);}
     }
     if(result!=null){cache[completed]=new int[result.Count];result.CopyTo(cache[completed]);}
    }
    if(expected!=fixedDelay||fixedDelay>bound)throw new Exception("structure timing");delay[completed]=fixedDelay;completed++;
    if(completed%100==0)Console.WriteLine($"structures={completed}/{n} functions={records.Count} compositions={tuples} seconds={sw.Elapsed.TotalSeconds:F2}");
   }
   using(var w=new BinaryWriter(File.Create(output))){w.Write(0);w.Write(records.Count);foreach(var p in records){var q=p.Value;w.Write(p.Key);w.Write(q.T);w.Write(q.G);w.Write(q.Pins.A);w.Write(q.Pins.B);w.Write(q.Pins.C);w.Write(q.Pins.D);}}
   File.WriteAllText(output+".status.json",JsonSerializer.Serialize(new{status="COMPLETE_INPUT_EXPANSION_OF_ENUMERATED_STRUCTURES",found=false,states=records.Count,tuples,seconds=sw.Elapsed.TotalSeconds,bound,names=Names,costs=Costs,enumerated_structures=n,processed_structures=completed}));
  }
 }
}
