
    
    mapboxgl.accessToken = mapToken;
    const map = new mapboxgl.Map({
        container: 'map', 
        center: eachList.geometry.coordinates, 
        zoom: 9 
    });

    const marker1 = new mapboxgl.Marker({color : 'red'})
        .setLngLat(eachList.geometry.coordinates)
        .setPopup(new mapboxgl.Popup({offset: 25})
        .setHTML(`<h5>${eachList.title}</h5><p>Exact Location will be given after booking!</p>`))
        .addTo(map);
