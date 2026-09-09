from matplotlib import pyplot as plt


def plot_map(da, **kwargs):
    from cartopy import crs, feature
    
    y_range = da.lat.values[[0, -1]]
    x_range = da.lon.values[[0, -1]]
    
    if 'ax' not in kwargs:
        kwargs['ax'] = plt.axes(projection=crs.PlateCarree(), facecolor='k')
        
    props = dict(transform=crs.PlateCarree())
    props.update(kwargs)
    
    img = da.plot.imshow(**props)

    ax = kwargs['ax']
    ax.set_extent([*x_range, *y_range], crs=crs.PlateCarree())
    ax.add_feature(feature.LAND.with_scale('10m'), facecolor='k', zorder=5)
    ax.coastlines(lw=0.5, resolution='10m', zorder=6)
    
    return img


def add_point_to_map(ax, lon, lat, **kwargs):
    proj = ax.projection.__class__()
    props = dict(c='r', marker='o', ms=6, transform=proj, zorder=6)
    props.update(kwargs)
    return ax.plot(lon, lat, **props)
    
    
def add_city_point_to_map(ax, city_xy):
    add_point_to_map(ax, *city_xy, c='w')
    add_point_to_map(ax, *city_xy, marker='.', c='k')
   
 
def plot_map_with_line_plot_below(da_map, da_line=None, **map_kwargs):
    from cartopy import crs
    
    saint_malo = -2.0257, 48.6493
    guadaloupe = -61.551, 16.2650
    
    fig = plt.figure(figsize=[6, 6])
    ax = [
        plt.subplot2grid([3, 1], [0, 0], 2, fc='w', projection=crs.PlateCarree()),
        plt.subplot2grid([3, 1], [2, 0], 1, fc='w'),
    ]

    img = plot_map(
        da_map, 
        ax=ax[0],
        add_colorbar=False, 
        **map_kwargs)

    add_city_point_to_map(ax[0], saint_malo)
    add_city_point_to_map(ax[0], guadaloupe)

    if da_line is not None:
        ax[1].plot(da_line.lon.values, da_line.values)
    ax[1].set_xlabel('Distance along track (km)')

    fig.tight_layout()
    
    p0 = ax[0].get_position()
    cax = fig.add_axes([p0.x0 - 0.04, p0.y0, p0.width * 0.03, p0.height])
    img.colorbar = plt.colorbar(img, cax=cax)
    cax.yaxis.set_label_position('left')
    cax.yaxis.set_ticks_position('left')
    
    return fig, [img, ax[1]]