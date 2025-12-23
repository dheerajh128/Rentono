const express = require("express");
const router = express.Router({mergeParams:true});

const wrapAsync = require("../utilities/wrapAsync.js");
const {validateReview,isLoggedIn,isAuthor} = require("../middleware.js");
const { addReview, destroyReview } = require("../controllers/reviews.js");


//Reviews
//Post
router.post("/",isLoggedIn,validateReview,wrapAsync(addReview));

//delete reviews
router.delete("/:reviewId",isLoggedIn,isAuthor,wrapAsync(destroyReview))

module.exports = router