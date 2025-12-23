const express = require("express");
const router = express.Router({mergeParams:true});
const wrapAsync = require("../utilities/wrapAsync.js");

const { isLoggedIn,isOwner,validateListing } = require("../middleware.js");
const multer = require("multer");
const {storage} = require("../cloudConfig.js");
const upload = multer({storage});
const {index, renderNewForm, showNewForm, createListing, editListing, updateListing, destroyListing} = require("../controllers/listings.js");


router.get("/",wrapAsync(index));

//New Listing
router.get("/new",isLoggedIn,renderNewForm);

router.get("/:id",wrapAsync(showNewForm));

//Make new Listing and Submit
router.post("/",isLoggedIn,upload.single("listing[image]"),validateListing,wrapAsync(createListing));

//Edit Route
router.get("/:id/edit",isLoggedIn,isOwner, wrapAsync(editListing));

//Editing the new one and updating it 
router.put("/:id",isLoggedIn,isOwner,upload.single("listing[image]"),validateListing,wrapAsync(updateListing));

//Delete a listing 
router.delete("/:id",isLoggedIn,isOwner,wrapAsync(destroyListing));

module.exports = router;