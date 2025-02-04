# Icon P-1 Nano TGE
------------------------------------

Modified the MackieControl script to work better with the Icon P-1 Nano. 
I am open to suggestions and will try to implement them as best as i can!
Watch this repo to get notifications about updates!


## IF YOU HAVE ANY ISSUES:
- Please let me know! I will try to fix them as soon as possible!
- If you can, please provide the log file that is generated by Ableton Live:
    - Windows:  \Users\[username]\AppData\Roaming\Ableton\Live x.x.x\Preferences\Log.txt
    - Mac:  /Users/[username]/Library/Preferences/Ableton/Live x.x.x/Log.txt

- IMPORTANT: Rename the "Icon_P1_Nano_TGE-main" folder to "Icon_P1_Nano_TGE" (if you see it, do it)
- IF THE FADER DOESNT WORK : USE THE Custom_Mapping.imap file instead, and customize it to your needs. Also please report this as an issue because i dont know why this fix works.


## Current Features (WIP Docu) :



### PLAY BUTTON
- Play Button can work as Play/Pause Button
    - normal press = play/pause inplace
    - long press = play from marker (mouse click)

The custom version focus on current track control. Using the up down button next to the jog wheel and the wheel you can now scroll through all tracks without banking and also ableton scrolls the arranger view so the current selected track is always visible. I also added a custom mode that allows you to use the encoder 1 for panning, the next for sends and the rest for plugin params.

I think pressing the jog wheel toggles group folding, I fixed the code that sets loop start and end, so with the right button assignment you can now correctly set loop regions (the original implementation only allowed setting start and end earlier i think?)

Oh yeah and i fixed the display code, the external display now shows track colors and names correctly. Also, whenever you select a track using the arranger or any other means, this will be the controlled track on the nano. Which is great because the nano is so very fitting as transport and current track controller.

I also modified what exactly happens when you press play and stop button. So the play button now actually is a play and pause button iirc :D (without looking at my code/device because im out of town)

Oh and there's paging for sends or plugin params in the custom tge mode (yeah clever name i know)
(the above is temporarely taken from reddit :D )
## Settings (settings.py):
  - encoder sensitivity 

# Install:

- Download the repo as zip  
  ![image](https://github.com/user-attachments/assets/37dda2c8-60a3-4276-8f99-a6536e095f3e)



- Go into Live

  ![image](https://github.com/MrMatch246/Launchkey_MK3_TGE/assets/50702646/5290bc01-4248-4e5d-9a44-b5f9a80c7d3c)

- then

  ![image](https://github.com/MrMatch246/Launchkey_MK3_TGE/assets/50702646/559af2d9-a063-437a-b2fe-77be1f838203)

- open "Remote Scripts" in finder/explorer.
    - if there is no "Remote Scripts" folder, create one in the "User Library" folder

- Close Live
- If you download the repo:
    - Unzip the downloaded file and copy the "Icon_P1_Nano_TGE-main" folder that is itself CONTAINED in another "Icon_P1_Nano_TGE-main" folder into  the "Remote Scripts" folder
    - IMPORTANT: Rename the "Icon_P1_Nano_TGE-main" folder to "Icon_P1_Nano_TGE"
- If you download the release (Todo: Make that a thing)
    - Just unzip it in the the "Remote Scripts" folder
- To check if everything went right, open "User Library/Remote Scripts/Icon_P1_Nano_TGE/settings.py"
- It should look like this (or similar):  
  ![image](https://github.com/user-attachments/assets/a39dbfe0-ab77-4b95-9ecb-3c58e1be61cb)
  ![image](https://github.com/user-attachments/assets/3679cf1e-9fc8-4fb5-80ad-5268caf07056)






- Start Live and select it

![image](https://github.com/user-attachments/assets/2aedf1e2-0bad-4e28-9cf9-f6100fadc5bf)


- ### Device settings should look like this:

  ![image](https://github.com/user-attachments/assets/9309d13e-de6f-427c-be9a-eecebe91201b)

