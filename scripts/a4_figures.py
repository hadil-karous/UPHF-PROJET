"""Export presentation figures from measured A4 evidence only."""
import argparse,json,pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from a4_data import dataset
p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args();out=pathlib.Path(a.source)
d=dataset(out);assert d['validated'];(out/'dashboard-data.json').write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
labels=['CPM émis','Copies ROS','Réceptions\nradio F2MD','R2 décodés','Contrôlés']
values=[d['metrics'][k] for k in ['cpm_tx','ros_cpm_copies','radio_rx','decoded','controlled']]
axes[0].bar(labels,values,color=['#167d91','#64748b','#167d91','#167d91','#167d91']);axes[0].set_ylabel('Messages observés')
for i,v in enumerate(values):axes[0].text(i,v+.5,str(v),ha='center')
names=list(dict.fromkeys(c['check'] for c in d['checks']));bottom=[0]*len(names)
for status,color in [('passed','#167d91'),('anomaly','#df8d44'),('non_evaluable','#9b91b8')]:
    v=[next((c['count'] for c in d['checks'] if c['check']==k and c['status']==status),0) for k in names]
    axes[1].barh(names,v,left=bottom,color=color,label=status);bottom=[x+y for x,y in zip(bottom,v)]
axes[1].legend(loc='lower right',fontsize=8);axes[1].set_xlabel('Occurrences de contrôle (pas des attaques)')
fig.suptitle('ExFMD-CP A4 · chaîne vivante CARLA–SUMO–ROS 2–Artery–F2MD\n'+d['case'])
fig.savefig(out/'presentation-a4.png',dpi=160);fig.savefig(out/'presentation-a4.svg');plt.close(fig)
print(json.dumps({'figure':str(out/'presentation-a4.png'),'metrics':d['metrics']}))
