import pathlib,csv,json,os,sys
os.environ['MPLCONFIGDIR']='/tmp/exfmd-mpl'
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
root=pathlib.Path('/repo/results/integrated')
for folder in root.iterdir():
    if not (folder/'positions.csv').exists():continue
    rows=list(csv.DictReader((folder/'positions.csv').open()))
    if not rows:continue
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    for sid in sorted({r['sumo_id'] for r in rows}):
        pts=[r for r in rows if r['sumo_id']==sid];t=[float(r['sumo_time']) for r in pts]
        axes[0].plot([float(r['x']) for r in pts],[-float(r['y']) for r in pts],'.-',label=sid)
        axes[1].plot(t,[float(r['speed_m_s']) for r in pts],label=sid)
        axes[2].plot(t,[float(r['sync_position_error_m']) for r in pts],label=sid)
    for ax in axes:ax.grid(alpha=.25);ax.legend()
    axes[0].set(xlabel='CARLA x (m)',ylabel='-CARLA y (m)',title='Measured trajectories');axes[0].axis('equal')
    axes[1].set(xlabel='SUMO simulation time (s)',ylabel='Speed (m/s)',title='SUMO vehicle speeds')
    axes[2].set(xlabel='SUMO simulation time (s)',ylabel='Position discrepancy (m)',title='CARLA pose vs converted SUMO pose')
    fig.tight_layout();fig.savefig(folder/'measurements.png',dpi=150);fig.savefig(folder/'measurements.svg');plt.close(fig)
    if (folder/'lidar.ply').exists():
        text=(folder/'lidar.ply').read_text().split('end_header\n',1)[1]
        pts=np.array([[float(x) for x in line.split()[:3]] for line in text.splitlines() if line.strip()])
        fig=plt.figure(figsize=(8,6));ax=fig.add_subplot(projection='3d');ax.scatter(*pts.T,c=pts[:,2],s=3,cmap='viridis');ax.set(xlabel='Sensor x (m)',ylabel='Sensor y (m)',zlabel='Sensor z (m)',title='CARLA LiDAR sample');fig.tight_layout();fig.savefig(folder/'lidar.png',dpi=150);plt.close(fig)
    print('Plots exported:',folder.name)
