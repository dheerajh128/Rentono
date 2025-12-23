const Listing = require("./models/listing");
const Review = require("./models/review");
const {listingSchema,reviewSchema} = require("./schema.js");
const ExpressError = require("./utilities/ExpressError.js");

module.exports.isLoggedIn = (req,res,next)=>{
    if(!req.isAuthenticated()){
        if (req.method === "DELETE" && req.params.id) {
            // Redirect back to listing page, not delete route
            req.session.RedirectUrl = `/listings/${req.params.id}`;
        } 
        else if (req.method === "GET") {
            req.session.RedirectUrl = req.originalUrl;
        }
        req.flash("error","Please login to do some changes in  listings!");
        return res.redirect("/login");
    }
    
        next();
    
    
}

module.exports.saveRedirectUrl = (req,res,next)=>{
    if(req.session.RedirectUrl){
        res.locals.RedirectUrl = req.session.RedirectUrl;
    }
    next();
}

module.exports.isOwner = async (req,res,next)=>{
    let {id} = req.params;
    let listing = await Listing.findById(id);
    if(!listing.owner._id.equals(res.locals.currentUser._id)){
        req.flash("error","You are not the owner of this listing!");
        return res.redirect(`/listings/${id}`);
    }
    next();
}

module.exports.validateListing = (req,res,next)=>{
    let {error} = listingSchema.validate(req.body);
    if(error){
        let errMsg = error.details.map((el)=>el.message).join(",");
        throw new ExpressError(400,errMsg);
    }else{
        next();
    }
}

module.exports.validateReview = (req,res,next)=>{
    let {error} = reviewSchema.validate(req.body);
    if(error){
        let errMsg = error.details.map((el)=>el.message).join(",");
        throw new ExpressError(400,errMsg);
    }else{
        next();
    }
}

module.exports.isAuthor = async (req,res,next)=>{
    let {id,reviewId} = req.params;
    let review = await Review.findById(reviewId);
    if(!review.author._id.equals(res.locals.currentUser._id)){
        req.flash("error","You did not review this!");
        return res.redirect(`/listings/${id}`);
    }
    else{
        next();
    }
    
}