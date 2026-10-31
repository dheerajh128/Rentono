const Listing = require("../models/listing.js");
const { searchAI } = require("../utilities/aiClient.js");
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

const MAX_AI_QUERY_LENGTH = 500;
const LISTING_ID = /^[a-fA-F0-9]{24}$/;
const UNAVAILABLE_MESSAGE = "Smart search is unavailable right now. You can still search by property title.";

function aiPage(fields){
    return {
        search: "",
        notice: null,
        summary: null,
        cards: [],
        showEmpty: false,
        titleSearchHref: null,
        ...fields,
    };
}

function validationNotice(detail){
    if(detail === "too_long"){
        return "Smart search accepts up to 500 characters.";
    }
    return "Enter a search to use smart search.";
}

function usableText(value){
    if(typeof value !== "string"){
        return null;
    }
    const text = value.trim();
    return text || null;
}

function usableScore(value){
    if(typeof value !== "number" || !Number.isFinite(value)){
        return null;
    }
    if(value < 0 || value > 1){
        return null;
    }
    return value;
}

function titleSearchLink(query){
    return `/listings/search?search=${encodeURIComponent(query)}`;
}

function canRenderListing(listing){
    if(!listing || typeof listing.title !== "string"){
        return false;
    }
    if(!listing.image || typeof listing.image.url !== "string"){
        return false;
    }
    if(!/^https?:\/\//i.test(listing.image.url)){
        return false;
    }
    if(typeof listing.price !== "number" || !Number.isFinite(listing.price)){
        return false;
    }
    return true;
}

function rankedFromOutcome(results){
    const ranked = [];
    const seen = new Set();
    for(const item of results){
        if(!item || typeof item._id !== "string" || !LISTING_ID.test(item._id)){
            continue;
        }
        const id = item._id.toLowerCase();
        if(seen.has(id)){
            continue;
        }
        seen.add(id);
        ranked.push({
            _id: id,
            score: usableScore(item.score),
            reason: usableText(item.reason),
        });
    }
    return ranked;
}

module.exports.aiSearch = async (req,res)=>{
    const rawSearch = req.query.search;

    if(typeof rawSearch !== "string"){
        return res.render("listings/ai-search.ejs", aiPage({
            notice: validationNotice("not_a_string"),
        }));
    }

    const search = rawSearch.trim();
    if(!search){
        return res.render("listings/ai-search.ejs", aiPage({
            notice: validationNotice("empty"),
        }));
    }
    if(search.length > MAX_AI_QUERY_LENGTH){
        return res.render("listings/ai-search.ejs", aiPage({
            notice: validationNotice("too_long"),
        }));
    }

    let outcome;
    try{
        outcome = await searchAI(search);
    }catch{
        console.error("ai_search_unavailable");
        return res.render("listings/ai-search.ejs", aiPage({
            search,
            notice: UNAVAILABLE_MESSAGE,
            titleSearchHref: titleSearchLink(search),
        }));
    }

    if(!outcome || outcome.status === "invalid_input"){
        return res.render("listings/ai-search.ejs", aiPage({
            notice: validationNotice(outcome && outcome.detail),
        }));
    }

    if(!outcome.ok || outcome.status === "invalid_config" || outcome.status === "unavailable"){
        console.error(typeof outcome.code === "string" ? outcome.code : "ai_search_unavailable");
        return res.render("listings/ai-search.ejs", aiPage({
            search,
            notice: UNAVAILABLE_MESSAGE,
            titleSearchHref: titleSearchLink(search),
        }));
    }

    const summary = usableText(outcome.summary);

    if(outcome.status === "agent_error" || outcome.status === "empty"){
        return res.render("listings/ai-search.ejs", aiPage({
            search,
            summary,
            showEmpty: true,
        }));
    }

    if(outcome.status !== "results" || !Array.isArray(outcome.results)){
        console.error("ai_search_malformed");
        return res.render("listings/ai-search.ejs", aiPage({
            search,
            notice: UNAVAILABLE_MESSAGE,
            titleSearchHref: titleSearchLink(search),
        }));
    }

    const ranked = rankedFromOutcome(outcome.results);
    if(ranked.length === 0){
        return res.render("listings/ai-search.ejs", aiPage({
            search,
            summary,
            showEmpty: true,
        }));
    }

    const docs = await Listing.find({
        _id: { $in: ranked.map((item) => item._id) },
    });
    const byId = new Map();
    for(const doc of docs){
        byId.set(String(doc._id).toLowerCase(), doc);
    }

    const cards = [];
    for(const item of ranked){
        const listing = byId.get(item._id);
        if(!canRenderListing(listing)){
            continue;
        }
        cards.push({
            listing,
            score: item.score,
            reason: item.reason,
        });
    }

    return res.render("listings/ai-search.ejs", aiPage({
        search,
        summary,
        cards,
        showEmpty: cards.length === 0,
    }));
}

module.exports.filterByCategory = async(req,res)=>{

    let {category} = req.params;

    let lists = await Listing.find({category});

    res.render("listings/lists.ejs",{
        lists,
        selectedCategory: category
    });

}