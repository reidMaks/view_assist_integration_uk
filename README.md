# Welcome

Welcome to the long awaited, much anticipated View Assist integration beta!  Some of the notable improvements include:

* All configuration done within the integration.  The days of editing YAML files are over!
* The View Assist dashboard is now autocreated when a View Assist device with visual output is configured
* Views can now be updated through an action call
* Users can create their own views as before and use a save view action that will store a local copy that will then be used when an autoregeneration of the dashboard action is called
* The external python set_state.py and control blueprint per device are no longer needed
* Some external pyscripts have now been integrated simplifying the install process
* Full support for both BrowserMod and the new [Remote Assist Display](https://github.com/michelle-avery/remote-assist-display)
* Many quality of life improvements have been added on both the user and developer facing sides

A HUGE thank you goes out to Mark Parker @msp1974 for his MASSIVE help with making this a reality.  Mark has written the majority of the integration with my guidance.  You should check out his [Home Assistant Integration Examples](https://github.com/msp1974/HAIntegrationExamples) Github if you are intestered in creating your own integration.  His work has propelled View Assist to first class in very short order.  We would not be where we are today without his continued efforts and the hours and hours he has put in to make View Assist better!  Thanks again Mark!



# Install

## Notes for existing VA users

**A BIG warning for folks who will be updating.  This is a major rewrite so you will be starting from scratch for the most part.  You will definitely want to do a backup of your current VA settings and views and possibly save a copy of your current dashboard to avoid from losing something you would like to keep!**

You will want to delete your View Assist dashboard before installing.  You will need to UPDATE your View Assist blueprints using the new blueprints.  This is done by importing the new version of the blueprint and choosing to update the existing.  This SHOULD allow for you to keep all settings but be warned that this is beta so problems may exist with keeping these settings in some cases.


## HACS
* Install HACS if you have not already

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dinki&repository=https%3A%2F%2Fgithub.com%2Fdinki%2Fview_assist_integration)

* Click Open your Home Assistant instance and open a repository inside the Home Assistant Community Store. 
to add this as a custom repository, or add it manually.
* Click "Add" to confirm, and then click "Download" to download and install the integration
Restart Home Assistant
* Search for "View Assist" in HACS and install then restart

## Manual Install

This integration can be installed by downloading the [view_assist](https://github.com/dinki/view_assist_integration/tree/main/custom_components) directory into your Home Assistant /config/custom_components directory and then restart Home Assistant.  We have plans to make this easier through HACS but are waiting for acceptance.

Questions, problems, concerns?  Reach out to us on Discord or use the 'Issues' above
