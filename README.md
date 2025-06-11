Simple version: I was going to construct a clone of the Yaesu FH-2 remote control for my transceiver (Yaesu FT-710) but I kept forgetting to order the parts.
It occured to me this evening that I should be able to duplicate the functionality using CAT commands and thus save yet another cable trailing across my desk to become entangled and possibly lost forever down the back of the desk.

The code works currently, but is not complete.

![image](https://github.com/user-attachments/assets/a6623923-093b-4aba-94e6-fde52bbcd427)

You can press 1-5 to playback the messages stored in the radio, MEM then 1-5 to record that message.  P/B then 1-5 also plays back the message.
In a fully functional FH-2, pressing 1-5 on their own has different meanings which I need to code.

I use a serial port splitter application for Windows ("Virtual Serial Ports Emulator") by Eterlogic Software https://www.eterlogic.com which allows multiple programs to share the serial ports.
![image](https://github.com/user-attachments/assets/1698b7b2-5aa5-4b99-82d7-fab8b43a57e1)

Should you install that software, here are the steps to create the two serial devices (standard (COM6 on my system) and enhanced (COM7 on my system)):
Device - Create New Device - Virtual Splitter - and then settings as this screen ![image](https://github.com/user-attachments/assets/6bf7e666-282b-4e7d-ab31-f07b5e256b9f)

With this you can connect (for example) FLRIG and multiple other software at the same time.

Anyway, it is 1 AM here and I am going to sleep.

Enjoy the code, it should not be difficult to modify for other radios, pull requests are welcomed.

