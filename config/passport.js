const passport = require("passport");

const LocalStrategy = require("passport-local");

const GoogleStrategy = require("passport-google-oauth20").Strategy;

const User = require("../models/user.js");

passport.use(new LocalStrategy(User.authenticate()));

passport.use(new GoogleStrategy({

    clientID: process.env.GOOGLE_CLIENT_ID,

    clientSecret: process.env.GOOGLE_CLIENT_SECRET,

    callbackURL: "http://localhost:8080/auth/google/callback"

},
async(accessToken,refreshToken,profile,done)=>{

    try{

        let existingUser = await User.findOne({
            googleId: profile.id
        });

        if(existingUser){

            return done(null,existingUser);

        }

        let userEmail = profile.emails[0].value;

        let alreadyRegistered = await User.findOne({
            email:userEmail
        });

        if(alreadyRegistered){

            alreadyRegistered.googleId = profile.id;

            await alreadyRegistered.save();

            return done(null,alreadyRegistered);

        }

        const newUser = new User({

            username: profile.displayName,

            email: userEmail,

            googleId: profile.id

        });

        await newUser.save();

        done(null,newUser);

    }catch(err){

        done(err,null);

    }

}));

passport.serializeUser(User.serializeUser());

passport.deserializeUser(User.deserializeUser());