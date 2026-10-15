"""Metadata/NLDM reader for the supported combinational technology aliases.

Tables and metadata are converted to ps/fF for structure scoring. Pin capacitance
ranges use the upper endpoint for max-delay analysis. OpenSTA reads native units.
"""
from pathlib import Path
import math
import re
from . import nldm as b
def clean(text):
    text = re.sub('/\\*.*?\\*/|//[^\\n]*', '', text, flags=re.S)
    return re.sub('\\\\\\r?\\n', '', text)

def units(text):

    def scale(value, scales):
        m = re.fullmatch('([0-9.eE+-]+)\\s*([a-zA-Z]+)', value or '')
        if not m or m[2].lower() not in scales:
            raise ValueError('Unsupported Liberty unit: ' + str(value))
        v = float(m[1]) * scales[m[2].lower()]
        if v <= 0:
            raise ValueError('Nonpositive unit')
        return v
    time_ps = scale(b.attr(text, 'time_unit'), dict(s=1000000000000.0, ms=1000000000.0, us=1000000.0, ns=1000.0, ps=1, fs=0.001))
    m = re.search('capacitive_load_unit\\s*\\(\\s*([0-9.eE+-]+)\\s*,\\s*"?([a-zA-Z]+)"?\\s*\\)', text)
    if not m:
        raise ValueError('Missing Liberty capacitance unit')
    cap_ff = scale(m[1] + m[2], dict(f=1000000000000000.0, mf=1000000000000.0, uf=1000000000.0, nf=1000000.0, pf=1000.0, ff=1, af=0.001))
    return dict(time_ps=time_ps, cap_ff=cap_ff)

def vector(body,key):
    m=re.search(r'\b'+key+r'\s*\(\s*"([^"]+)"',body)
    return [float(v) for v in re.findall(b.NUM,m[1])] if m else None

def pin_capacitance(body, key, default):
    """Match OpenSTA max-path loading, including Liberty capacitance ranges."""
    value = float(b.attr(body, key, default))
    interval = re.search(r'\b' + key + r'_range\s*\(([^)]*)\)', body)
    if interval:
        values = [float(v) for v in re.findall(b.NUM, interval[1])]
        if len(values) != 2 or not 0 <= values[0] <= values[1]:
            raise ValueError('Invalid ' + key + '_range')
        value = values[1]
    if not math.isfinite(value) or value < 0:
        raise ValueError('Nonfinite or negative pin capacitance')
    return value

def read_library(path,sizing=False):
    text=clean(Path(path).read_text());u=units(text)
    templates=dict(b.groups(text,'lu_table_template'));result={}
    allowed={k+'_X'+str(s) for k in b.CELL_NAMES for s in ((1,2,4) if sizing else (1,))}
    for name,body in b.groups(text,'cell'):
        if name not in allowed:continue
        pins={};arcs=[];outputs=[]
        for pin,pb in b.groups(body,'pin'):
            if b.attr(pb,'direction')=='input':
                cap=float(b.attr(pb,'capacitance'))
                if cap<0:raise ValueError('Negative pin capacitance in '+name)
                pins[pin]=[u['cap_ff']*pin_capacitance(pb,k,cap) for k in ('rise_capacitance','fall_capacitance')]
            elif b.attr(pb,'direction')=='output':
                outputs.append(pin)
                for _,ab in b.groups(pb,'timing'):
                    if b.attr(ab,'timing_type','combinational') not in ('combinational','combinational_rise','combinational_fall'):raise ValueError('Unsupported arc type in '+name)
                    tables=[]
                    if b.attr(ab,'timing_sense') not in ('positive_unate','negative_unate','non_unate'):
                        raise ValueError('Unsupported timing sense in '+name)
                    for kind in b.KINDS:
                        entries=list(b.groups(ab,kind))
                        if len(entries)!=1:raise ValueError('Expected full NLDM timing arc in '+name)
                        template,tb=entries[0];templ=templates[template]
                        variables=[b.attr(templ,'variable_'+str(j)) for j in (1,2)]
                        a=vector(tb,'index_1') or vector(templ,'index_1');c=vector(tb,'index_2') or vector(templ,'index_2')
                        z=[float(v)*u['time_ps'] for line in re.findall(r'"([^"]+)"',tb.split('values',1)[1]) for v in re.findall(b.NUM,line)]
                        if variables[0]=='total_output_net_capacitance':
                            a,c=c,a;z=[z[i*len(a)+j] for j in range(len(a)) for i in range(len(c))];variables.reverse()
                        if variables[0] not in ('input_transition_time','input_net_transition') or variables[1]!='total_output_net_capacitance':raise ValueError('Unsupported NLDM axes')
                        tables.append(b.Table([x*u['time_ps'] for x in a],[x*u['cap_ff'] for x in c],z))
                    arcs.append(dict(pin=b.attr(ab,'related_pin'),sense=b.attr(ab,'timing_sense'),when=b.attr(ab,'when'),tables=tables))
        if len(outputs)!=1 or not arcs or {a['pin'] for a in arcs}!=set(pins):raise ValueError('Unsupported cell '+name)
        result[name]=dict(pins=pins,output=outputs[0],arcs=arcs,area=float(re.search(r'\barea\s*:\s*('+b.NUM+r')',body)[1]))
    if not {'INV_X1','BUF_X1'}<=result.keys():raise ValueError('Canonical gate aliases are required')
    return result
