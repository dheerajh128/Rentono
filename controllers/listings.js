const Listing = require("../models/listing.js");
const mbxGeocoding = require('@mapbox/mapbox-sdk/services/geocoding');
const mapToken = process.env.MAP_TOKEN;
const geocodingClient = mbxGeocoding({ accessToken: mapToken });

module.exports.index = async (req,res)=>{
    let lists = await Listing.find({});
    res.render("listings/lists.ejs",{
        lists,
        selectedCategory:""
    });
}

module.exports.renderNewForm = (req,res)=>{
    res.render("listings/newlisting.ejs");
}

module.exports.showNewForm = async (req,res)=>{
    let {id} = req.params;
    let eachList = await Listing.findById(id)
    .populate({path:"reviews",populate:{path:"author"}})
    .populate("owner");
    if(!eachList){
        req.flash("error","The Listing you asked for does not exist");
        return res.redirect("/listings")
    }
    res.render("listings/eachlist.ejs",{eachList});
}

module.exports.createListing = async (req,res,next)=>{
    let coordinates = await geocodingClient.forwardGeocode({
        query: req.body.listing.location,
        limit: 1
    })
    .send()
  
    let url = req.file.path;
    let filename = req.file.filename;
    let newListing = new Listing(req.body.listing);
    newListing.owner = req.user._id;
    newListing.image = {url,filename};
    newListing.geometry = coordinates.body.features[0].geometry;
    await newListing.save();
    req.flash("success","New Listing is Created!!")
    res.redirect("/listings");
}

module.exports.editListing = async (req,res)=>{
    let {id} = req.params;
    let thisUser = await Listing.findById(id);
    if(!thisUser){
        req.flash("error","The Listing you asked for does not exist");
        return res.redirect("/listings")
    }
    let originalUrl = thisUser.image.url;
    originalUrl = originalUrl.replace("/upload","/upload/c_fill,h_300,w_250")
    res.render("listings/editlisting.ejs" ,{thisUser,originalUrl});
}

module.exports.updateListing = async (req,res)=>{
    let {id} = req.params;
    let listing = await Listing.findByIdAndUpdate(id,{...req.body.listing});

    if(typeof req.file != "undefined"){
        let url = req.file.path;
        let filename = req.file.filename;
        listing.image = {url,filename};
        await listing.save();
    }
     req.flash("success","Listing is Edited!!")
     res.redirect(`/listings/${id}`);
}

module.exports.destroyListing = async (req,res)=>{
    let {id} = req.params;
    
     await Listing.findByIdAndDelete(id);
     req.flash("success","Listing is Deleted!!")
     res.redirect("/listings");
}

module.exports.searchListings = async (req,res)=>{
    let {search} = req.query;

    let searchedListings = await Listing.find({
        title : {$regex : search , $options : "i"}
    });

    res.render("listings/search.ejs",{searchedListings,search});
}

module.exports.filterByCategory = async(req,res)=>{

    let {category} = req.params;

    let lists = await Listing.find({category});

    res.render("listings/lists.ejs",{
        lists,
        selectedCategory: category
    });

}