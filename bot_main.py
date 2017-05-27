import asyncio
import concurrent.futures
import json
import sys
import time
import traceback

import discord
import websockets.exceptions

import main_code.command_decorator
import main_code.commands.admin.broadcast
import main_code.commands.admin.change_icon
import main_code.commands.admin.repl
from main_code import helpers

# Setting up the client object
client = helpers.actual_client


@client.event
async def on_message(message: discord.Message):
    # We wait for a split second so we can be assured that ignoring of messages and other things have finished before the message is processed here
    # We make sure the message is a regular one
    if message.type != discord.MessageType.default:
        return

    await asyncio.sleep(0.1)

    global config

    # The weird mention for the bot user (mention code starts with an exclamation mark instead of just the user ID), the string manipulation is due to mention strings not being the same all the time
    client_mention = client.user.mention[:2] + "!" + client.user.mention[2:]

    # Log the message using proper formatting techniques (and some sanity checking so we log our own sent messages separately)
    if not message.author.name == client.user.name:
        # We check if we should ignore the message
        if message.author.name not in config["log_config"]["ignored_log_user_names"]:
            # Someone sent a message in a server or channel we have joined / have access to
            if message.channel.is_private:
                helpers.log_info(message.author.name + " said: \"" + message.content + "\" in a PM.")
            else:
                if message.channel.name not in config["log_config"]["ignored_log_channels"]:
                    helpers.log_info(
                        message.author.name + " said: \"" + message.content + "\" in channel: \"" + message.channel.name + "\" on server \"" + message.server.name + "\".")

            # We check if there were any attachments to the message, and if so, we log all the relevant info we can get about the attachment
            if message.attachments:
                # We log that the user sent attachments
                helpers.log_info("{0:s} attached {1:d} file(s)".format(message.author.name, len(message.attachments)))

                # We loop through all the attachments
                for attachment in message.attachments:
                    # We check for the image/video-like attributes width and height (in pixels obviously) and we output them if they exist
                    if ("width" in attachment) and ("height" in attachment):
                        # We log the attachment as an image/video-like file
                        helpers.log_info(
                            "User {0:s} attached image/video-like file \"{1:s}\" of dimensions X: {2:d} and Y: {3:d} and filesize {4:d} bytes.".format(
                                message.author.name, attachment["filename"], attachment["width"], attachment["height"],
                                attachment["size"]))

                    else:
                        # We log the attachment as a unknown filetype
                        helpers.log_info(
                            "User {0:s} attached file \"{1:s}\" of filesize {2:d} bytes.".format(
                                message.author.name, attachment["filename"], attachment["size"]))

    else:
        # We sent a message and we are going to increase the sent messages counter in the config
        # We first load the config
        with open("config.json", mode="r", encoding="utf-8") as config_file:
            current_config = json.load(config_file)

        # Now we change the actual value and then dump it back into the file
        current_config["stats"]["messages_sent"] += 1

        with open("config.json", mode="w", encoding="utf-8") as config_file:
            # Dump back the changed data
            json.dump(current_config, config_file, indent=2)

        # We sent a message and we are going to log it appropriately
        if message.channel.is_private:
            helpers.log_info("We said: \"" + message.content + "\" in a PM to " + message.channel.user.name + ".")
        else:
            if message.channel.name not in config["log_config"]["ignored_log_channels"]:
                helpers.log_info(
                    "We said: \"" + message.content + "\" in channel: \"" + message.channel.name + "\" on server \"" + message.server.name + "\".")

    # Checking if the user used a command, but we first wait to make sure that the message gets ignored if necessary
    await asyncio.sleep(0.2)

    # We need to define all the special params as globals to be able to access them without sneaky namespace stuff biting us in the ass
    global ignored_command_message_ids

    # We define the list of special parameters that may be sent to the message functions, and also have to be returned from them (in a list)
    special_params = [ignored_command_message_ids, config]

    # Checking if we sent the message, so we don't trigger ourselves and checking if the message should be ignored or not (such as it being a response to another command)
    # We also check if the message was sent by a bot account, as we don't allow them to use commands
    if not ((message.author.id == client.user.id) or (message.id in ignored_command_message_ids) or message.author.bot):
        # If a command is used with the message that was passed to the event, we know that a command has been triggered
        used_command = False

        # Check if the message was sent in a PM to fluxx
        if message.channel.is_private:

            # Going through all the public commands we've specified and checking if they match the message
            for command in public_commands:
                if message.content.lower().strip().startswith(command["command"]):
                    # We log what command was used by who
                    helpers.log_info("The " + command[
                        "command"] + " command was triggered by \"" + message.author.name + "\" in a PM.")

                    # The command matches, so we call the method that was specified in the command list
                    temp_result = await command["method"](message, client, config,
                                                          *[x[0] for x in
                                                            zip(special_params,
                                                                command["special_params"])
                                                            if x[1]])
                    x = 0
                    # We put back all the values that we got returned
                    if temp_result:
                        for i in range(len(special_params)):
                            if command["special_params"][i]:
                                set_special_param(i, temp_result[x])
                                x += 1

                    # We note that a command was triggered so we don't output the message about what "!" means
                    used_command = True
                    break

            # Checking if the issuing user is in the admin list
            if helpers.is_member_fluxx_admin(message.author, config):

                # Going through all the admin commands we've specified and checking if they match the message
                for command in admin_commands:
                    if message.content.lower().strip().startswith("admin " + command["command"]):
                        # We log what command was used by who
                        helpers.log_info("The " + command[
                            "command"] + " admin command was triggered by admin \"" + message.author.name + "\" in a PM.")

                        # The command matches, so we call the method that was specified in the command list
                        temp_result = await command["method"](message, client, config, *[x[0] for x in
                                                                                         zip(special_params,
                                                                                             command["special_params"])
                                                                                         if x[1]])
                        x = 0
                        # We put back all the values that we got returned
                        if temp_result:
                            for i in range(len(special_params)):
                                if command["special_params"][i]:
                                    set_special_param(i, temp_result[x])
                                    x += 1

                        # We note that a command was triggered so we don't output the message about what fluxx can do
                        used_command = True
                        break

            # If the message started with an command trigger and it didn't have a valid command we try to teach the user which commands are available
            if not used_command:
                # Sending the message to the user
                await client.send_message(message.channel,
                                          "You seemingly just tried to use an " + client_mention + " command, but I couldn't figure out which one you wanted to use, if you want to know what commands I can do for you, please type \"" + client_mention + " help\" :smile:")
            else:
                # If the message was a command of any sort, we increment the commands received counter on fluxx
                # We first load the config
                with open("config.json", mode="r", encoding="utf-8") as config_file:
                    current_config = json.load(config_file)

                # Now we change the actual value and then dump it back into the file
                current_config["stats"]["commands_received"] += 1

                with open("config.json", mode="w", encoding="utf-8") as config_file:
                    # Dump back the changed data
                    json.dump(current_config, config_file, indent=2)

        # We're in a regular server channel
        else:
            # Checking if the message is a command, (starts with a mention of fluxx)
            if helpers.is_message_command(message, client):
                # Going through all the public commands we've specified and checking if they match the message
                for command in public_commands:
                    if helpers.remove_fluxx_mention(client, message).lower().strip().startswith(
                            command["command"]):
                        # We log what command was used by who and where
                        helpers.log_info("The " + command[
                            "command"] + " command was triggered by \"" + message.author.name + "\" in channel \"" + message.channel.name + "\" on server \"" + message.server.name + "\".")

                        # The command matches, so we call the method that was specified in the command list
                        temp_result = await command["method"](message, client, config, *[x[0] for x in
                                                                                         zip(special_params,
                                                                                             command["special_params"])
                                                                                         if x[1]])
                        x = 0
                        # We put back all the values that we got returned
                        if temp_result:
                            for i in range(len(special_params)):
                                if command["special_params"][i]:
                                    set_special_param(i, temp_result[x])
                                    x += 1

                        # We note that a command was triggered so we don't output the message about what fluxx can do
                        used_command = True
                        break

                # Checking if the issuing user is in the admin list
                if helpers.is_member_fluxx_admin(message.author, config):
                    # Going through all the admin commands we've specified and checking if they match the message
                    for command in admin_commands:
                        if helpers.remove_fluxx_mention(client, message).lower().strip().startswith(
                                        "admin " + command["command"]):

                            # We check if the command was triggered in a private channel/PM or not
                            if message.channel.is_private:

                                # We log what command was used by who
                                helpers.log_info("The " + command[
                                    "command"] + " admin command was triggered by admin \"" + message.author.name + "\" in a PM.")

                            else:
                                # We log what command was used by who and where
                                helpers.log_info("The " + command[
                                    "command"] + " admin command was triggered by admin \"" + message.author.name + "\" in channel \"" + message.channel.name + "\" on server \"" + message.server.name + "\".")

                            # The command matches, so we call the method that was specified in the command list
                            temp_result = await command["method"](message, client, config, *[x[0] for x in
                                                                                             zip(special_params,
                                                                                                 command[
                                                                                                     "special_params"])
                                                                                             if x[1]])
                            x = 0
                            # We put back all the values that we got returned
                            if temp_result:
                                for i in range(len(special_params)):
                                    if command["special_params"][i]:
                                        set_special_param(i, temp_result[x])
                                        x += 1

                            # We note that a command was triggered so we don't output the message about what fluxx can do
                            used_command = True
                            break

                # If the message started with an command trigger and it didn't have a valid command we try to teach the user which commands are available
                if not used_command:
                    # Sending the message to the user
                    await client.send_message(message.channel,
                                              message.author.mention + ", you seemingly just tried to use an " + client_mention + " command, but I couldn't figure out which one you wanted to use, if you want to know what commands I can do for you, please type \"" + client_mention + " help\" :smile:")
                else:
                    # If the message was a command of any sort, we increment the commands received counter on fluxx
                    # We first load the config
                    with open("config.json", mode="r", encoding="utf-8") as config_file:
                        current_config = json.load(config_file)

                    # Now we change the actual value and then dump it back into the file
                    current_config["stats"]["commands_received"] += 1

                    with open("config.json", mode="w", encoding="utf-8") as config_file:
                        # Dump back the changed data
                        json.dump(current_config, config_file, indent=2)

                    # We remove stream players that are done playing, as this is done on every command and every commands can only create at most 1 stream player, we guarantee no memory leak
                    server_and_stream_players[:] = [x for x in server_and_stream_players if not x[1].is_done()]

    else:
        # Checking if we didn't check if the message was a command because the message id was in the ignored ids list
        if message.id in ignored_command_message_ids:
            # We remove the ignored id from the list so we don't accumulate ids to check against
            ignored_command_message_ids.remove(message.id)


@client.event
async def on_member_join(member: discord.Member):
    """This event is called when a member joins a server, we use it for various features."""

    # We wait as to not do stuff before the user has actually joined the server
    await asyncio.sleep(0.2)

    # We log that a user has joined the server
    helpers.log_info(
        "User {0:s} ({1:s}) has joined server {2:s} ({3:s}).".format(member.name, member.id, member.server.name,
                                                                     member.server.id))

    # We call all the join functions, and pass them the member who joined
    for join_function in join_functions:
        await join_function(member)


@client.event
async def on_member_remove(member: discord.Member):
    """This event is called when a member leaves a server, we use it for various features."""

    # We log that a user has left the server
    helpers.log_info(
        "User {0:s} ({1:s}) has left server {2:s} ({3:s}).".format(member.name, member.id, member.server.name,
                                                                   member.server.id))

    # We check if the server is on the list of servers who use the leave message feature
    if int(member.server.id) in [x[0] for x in config["leave_msg"]["server_and_channel_id_pairs"]]:

        # We send a message to the specified channels in that server (you can have however many channels you want, but we check if they are on the correct server)
        channel_ids = \
            [x[1:] for x in config["leave_msg"]["server_and_channel_id_pairs"] if x[0] == int(member.server.id)][0]

        # We loop through all the possible channels and check if they're valid
        for channel_id in [int(x) for x in channel_ids]:
            # We check if the channel id is on the server that the member left
            if discord.utils.find(lambda c: int(c.id) == channel_id, member.server.channels) is not None:
                # We send the leave message:
                await client.send_message(discord.utils.find(lambda c: int(c.id) == channel_id, member.server.channels),
                                          config["leave_msg"]["leave_msg"].format(member.mention, member.server.name))


@client.event
async def on_ready():
    """This does various things that should be done on startup.
    One of them is outputting info about who we're logged in as."""
    helpers.log_info("fluxx-bot has now logged in as: {0} with id {1}".format(client.user.name, client.user.id))


async def join_welcome_message(member: discord.Member):
    """This function is called when a user joins a server, and welcomes them if the server has enabled the welcome message feature."""

    # We check if the server is on the list of servers who use the welcome message feature
    if int(member.server.id) in [x[0] for x in config["join_msg"]["server_and_channel_id_pairs"]]:

        # We send a message to the specified channels in that server (you can have however many channels you want, but we check if they are on the correct server)
        channel_ids = \
            [x[1:] for x in config["join_msg"]["server_and_channel_id_pairs"] if x[0] == int(member.server.id)][0]

        # We loop through all the possible channels and check if they're valid
        for channel_id in [int(x) for x in channel_ids]:
            # We check if the channel id is on the server that the member joined
            if discord.utils.find(lambda c: int(c.id) == channel_id, member.server.channels) is not None:
                # We send the welcome message:
                await client.send_message(discord.utils.find(lambda c: int(c.id) == channel_id, member.server.channels),
                                          config["join_msg"]["welcome_msg"].format(member.mention, member.server.name))


@client.event
async def on_error(event, *args, **kwargs):
    """This event is called when an error is raised by the client,
    and we override the default behaviour to be able to log and catch errors."""

    # We retrieve the exception we're handling
    e_type, e, e_traceback = sys.exc_info()

    # We log the event in different ways depending on the severity and type of error
    if isinstance(e, websockets.exceptions.ConnectionClosed) and (e.code == 1000):
        # This error is handlable and a result of the discord servers being flaky af
        helpers.log_info("Got websockets.exceptions.ConnectionClosed code 1000 from event {0}.".format(event))
    else:
        helpers.log_error("Ignoring exception in {0}, more info:\n{1}".format(event, "".join(
            ["    " + entry for entry in traceback.format_exception(e_type, e, e_traceback)])))


@main_code.command_decorator.command("help", "Do I really need to explain this...")
async def cmd_help(message: discord.Message, passed_client: discord.Client, passed_config: dict):
    """This method is called to handle someone needing information about the commands they can use fluxx for.
    Because of code simplicity this is one of the command functions that needs to stay in the __init__py file."""

    # We need to create the helptexts dynamically and on each use of this command as it depends on the bot user mention which needs the client to be logged in

    # The correct mention for the bot user, the string manipulation is due to mention strings not being the same depending on if a user or the library generated it
    client_mention = passed_client.user.mention[:2] + "!" + passed_client.user.mention[2:]

    # Generating the combined and formatted helptext of all the public commands (we do this in <2000 char chunks, as 2000 chars is the max length of a discord message)
    public_commands_helptext = [""]

    # The separator between help entries, it uses discord formatting to look nice
    help_separator = "__" + (" " * 98) + "__"

    # Looping through all the public commands to add their helptexts to the correct chunks
    for helpcommand in public_commands:

        # We check if the last chunk is too will become too large or not
        if len(public_commands_helptext[-1] + "\n" + help_separator + "\n\t" + "**" + helpcommand[
            "command"] + "**\n" + helpcommand["helptext"] + "\n" + help_separator) > 2000:
            # We add another string to he list of messages we want to send
            public_commands_helptext.append("")

        public_commands_helptext[-1] += "\n" + help_separator + "\n\t" + "**" + helpcommand[
            "command"] + "**\n" + helpcommand["helptext"]

    # Checking if the issuer is an admin user, so we know if we should show them the admin commands
    if int(message.author.id) in passed_config["somewhat_weird_shit"]["admin_user_ids"]:
        # Generating the combined and formatted helptext of all the admin commands (we do this in >2000 char chunks, as 2000 chars is the max length of a discord message)
        admin_commands_helptext = [""]

        # Looping through all the admin commands to add their helptexts to the correct chunks
        for helpcommand in admin_commands:

            # We check if the last chunk is too will become too large or not
            if len(admin_commands_helptext[-1] + "\n" + help_separator + "\n\t" + "*admin* **" + helpcommand[
                "command"] + "**\n" + helpcommand["helptext"] + "\n" + help_separator) > 2000:
                # We add another string to he list of messages we want to send
                admin_commands_helptext.append("")

            admin_commands_helptext[-1] += "\n" + help_separator + "\n\t" + "*admin* **" + helpcommand[
                "command"] + "**\n" + helpcommand["helptext"]

    # How many seconds we should wait between each message
    cooldown_time = 0.5

    # Checking if we're in a private channel or a public channel so we can format our messages properly
    if not message.channel.is_private:
        # Telling the user that we're working on it
        await passed_client.send_message(message.channel,
                                         "Sure thing " + message.author.mention + ", you'll see the commands and how to use them in our PMs :smile:")

    # Checking if the issuer is an admin user, so we know if we should show them the admin commands
    if int(message.author.id) in passed_config["somewhat_weird_shit"]["admin_user_ids"]:

        # Just putting the helptexts we made in the PM with the command issuer
        await passed_client.send_message(message.author, "Ok, here are the commands you can use me for :smile:")

        # We send the helptexts in multiple messages to bypass the 2000 char limit, and we pause between each message to not get rate-limited
        for helptext in public_commands_helptext:
            # We wait for a bit to not get rate-limited
            await asyncio.sleep(cooldown_time)

            # We send the help message
            await passed_client.send_message(message.author, helptext)

        # Informing the user that they're an admin
        await passed_client.send_message(message.author,
                                         help_separator + "\nSince you're an fluxx-bot admin, you also have access to:")

        for helptext in admin_commands_helptext:
            # We wait for a bit to not get rate-limited
            await asyncio.sleep(cooldown_time)

            # We send the help message
            await passed_client.send_message(message.author, helptext)

    else:

        # Just putting the helptexts we made in the PM with the command issuer
        await passed_client.send_message(message.author, "Ok, here are the commands you can use me for :smile:")

        # We send the helptexts in multiple messages to bypass the 2000 char limit, and we pause between each message to not get rate-limited
        for helptext in public_commands_helptext:
            # We wait for a bit to not get rate-limited
            await asyncio.sleep(cooldown_time)

            # We send the help message
            await passed_client.send_message(message.author, helptext)

    # Sending a finishing message (on how to use the commands in a regular channel)
    await passed_client.send_message(message.author,
                                     help_separator + "\nTo use commands in a regular server channel, just do \"" + client_mention + " **COMMAND**\"")


@main_code.command_decorator.command("reload config", "Reloads the config file that fluxx-bot uses.", admin=True)
async def cmd_admin_reload_config(message: discord.Message, passed_client: discord.Client, passed_config: dict):
    """This method is used to handle an admin user wanting us to reload the config file.
    Because of code simplicity this is one of the command functions that needs to stay in the __init__py file."""

    # Telling the issuing user that we're reloading the config
    # Checking if we're in a private channel or if we're in a regular channel so we can format our message properly
    if message.channel.is_private:
        await passed_client.send_message(message.channel, "Ok, I'm reloading it right now!")
    else:
        await passed_client.send_message(message.channel,
                                         "Ok " + message.author.mention + ", I'm reloading it right now!")

    # Telling the issuing user that we're reloading the config file
    await passed_client.send_message(message.channel, "Reloading the config file...")

    # Logging that we're loading the config
    helpers.log_info("Reloading the config file...")

    # Loading the config file and then parsing it as json and storing it in a python object
    with open("config.json", mode="r", encoding="utf-8") as opened_config_file:
        global config
        config = json.load(opened_config_file)

    # Logging that we're done loading the config
    helpers.log_info("Done reloading the config")

    # Telling the issuing user that we're done reloading the config file
    await passed_client.send_message(message.channel, "Done reloading the config file!")

    # Telling the issuing user that we're updating the vanity command dict
    await passed_client.send_message(message.channel, "Updating vanity commands...")

    # Logging that we're updating the vanity commands
    helpers.log_info("Updating vanity commands...")

    # Updating the vanity command dict because the config file could have changed the vanity setup
    await main_code.commands.regular.vanity_role_commands.update_vanity_dictionary(passed_client, passed_config)

    # Logging that we're done updating the vanity commands
    helpers.log_info("Done updating vanity commands")

    # Telling the issuing user that we're done updating the vanity command dict
    await passed_client.send_message(message.channel, "Done updating vanity commands!")

    # Telling the issuing user that we're reloading the config
    # Checking if we're in a private channel or if we're in a regular channel so we can format our message properly
    if message.channel.is_private:
        await passed_client.send_message(message.channel, "Ok, I'm done reloading now :smile:")
    else:
        await passed_client.send_message(message.channel,
                                         "Ok " + message.author.mention + ", I'm done reloading it now :smile:")


def set_special_param(index: int, value):
    """This function handles resolving a special param index into being able to set that variable (it can be immutable) to the inputted value.
    We need this function since python doesn't have a concept of references."""

    global ignored_command_message_ids
    global config

    # This code is really ugly because we need performance (dictionaries with lambdas with exec it very slow since it compiles every time we define it),
    # because python doesn't have any concept of references, and because python doesn't have any equivalent to switch/case
    if index == 0:
        ignored_command_message_ids = value
    elif index == 1:
        config = value


# We define the objects that we have to use in the file scope
# The config object
config = {}
# Public commands
public_commands = []
# Admin commands
admin_commands = []
# Functions to run when people join a server
join_functions = []
# Msg ideas that should be ignored
ignored_command_message_ids = []
# Voice stream players for each server
server_and_stream_players = []


def start_fluxx():
    """Starts fluxx-bot, and returns when fluxx exits. If fluxx throws an exception, this exception is propagated. If fluxx exits peacefully, this returns with no exception."""

    # Logging that we're loading the config
    helpers.log_info("Loading the config file...")

    # We make sure we use the global objects
    global config, public_commands, admin_commands, join_functions, ignored_command_message_ids, server_and_stream_players
    config = {}

    # Loading the config file and then parsing it as json and storing it in a python object
    with open("config.json", mode="r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    # We store the bot start time in the volatile stats section
    config["stats"]["volatile"]["start_time"] = time.time()

    # We write the modified config back to the file
    with open("config.json", mode="w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2, sort_keys=False)

    # Logging that we're done loading the config
    helpers.log_info("Done loading the config")

    commands = main_code.command_decorator.get_command_lists()

    # The commands people can use and the method that will be called when a command is used
    # The special params are defined in the on_message function, but they basically just pass all the special params as KW arguments
    # Most commands use the helpers.command(command_trigger, description, special_params, admin) decorator, but these cannot use that since they have config based command parameters
    public_commands = []

    # The commands authorised users can use, these are some pretty powerful commands, so be careful with which users you give administrative access to the bot to
    admin_commands = []

    # We extend the lists with the decorator commands
    public_commands.extend(commands[0])
    admin_commands.extend(commands[1])

    # The functions to call when someone joins the server, these get passed the member object of the user who joined
    join_functions = [join_welcome_message]

    # The list of message ids (this list will fill and empty) that the command checker should ignore
    ignored_command_message_ids = []

    # The list of tuples of voice stream players and server ids
    server_and_stream_players = []

    # Logging that we're starting the bot
    helpers.log_info("fluxx-bot is now logging in (you'll notice if we get any errors)")

    # Storing the time at which the bot was started
    config["stats"]["volatile"]["start_time"] = time.time()

    try:
        # We have a while loop here because some errors are only catchable from the client.run method, as they are raised by tasks in the event loop
        # Some of these errors are not, and shouldn't, be fatal to the bot, so we catch them and relaunch the client.
        # The errors we don't catch however, rise to the next try except and actually turn off the bot
        while True:
            try:
                # Starting and authenticating the bot
                client.run(config["credentials"]["token"])
            except concurrent.futures.TimeoutError:
                # We got a TimeoutError, which in general shouldn't be fatal.
                helpers.log_info("Got a TimeoutError from client.run, logging in again.")
            except discord.ConnectionClosed as e:
                # We got a ConnectionClosed error, which should mean that the client was disconnected from the websocket for un-handlable reasons
                # We reconnect if it's a handlable reason
                if e.code == 1000:
                    # We wait for a bit to not overload/ddos the discord servers if the problem is on their side
                    time.sleep(1)
                    helpers.log_info("Got a discord.ConnectionClosed code 1000 from client.run, logging in again.")
                else:
                    helpers.log_info("Got a discord.ConnectionClosed from client.run, but not logging in again.")
                    raise e
            except websockets.exceptions.ConnectionClosed as e:
                # We got a ConnectionClosed error, which should mean that the client was disconnected from the websocket for un-handlable reasons
                # We wait for a bit to not overload/ddos the discord servers if the problem is on their side
                if e.code == 1000:
                    # We wait for a bit to not overload/ddos the discord servers if the problem is on their side
                    time.sleep(1)
                    helpers.log_info(
                        "Got a websockets.exceptions.ConnectionClosed code 1000 from client.run, logging in again.")
                else:
                    helpers.log_info(
                        "Got a websockets.exceptions.ConnectionClosed from client.run, but not logging in again.")
                    raise e
            except ConnectionResetError:
                # We got a ConnectionReset error, which should mean that the client was disconnected from the websocket for un-handlable reasons
                # We wait for a bit to not overload/ddos the discord servers if the problem is on their side (((it is)))
                time.sleep(1)
                helpers.log_info("Got a ConnectionResetError from client.run, logging in again.")
            else:
                # If we implement a stop feature in the future, we will need this to be able to stop the bot without using exceptions
                break
    except:
        # How did we exit?
        helpers.log_warning("Did not get user interrupt, but still got an error, re-raising...")
        # Our code for the bot having exited because of an error
        exit_code = 11
    else:
        # No error but we exited
        helpers.log_info("Client exited, but we didn't get an error, probably CTRL+C or command exit...")
        exit_code = 0

    # Calculating and formatting how long the bot was online so we can log it, this is on multiple statements for clarity
    end_time = time.time()
    uptime_secs_noformat = (end_time - config["stats"]["volatile"]["start_time"]) // 1
    formatted_uptime = helpers.get_formatted_duration_fromtime(uptime_secs_noformat)

    # Logging that we've stopped the bot
    helpers.log_info(
        "fluxx-bot has now exited (you'll notice if we got any errors), we have been up for {0}.".format(
            formatted_uptime))

    # We exit with the proper code
    exit(exit_code)


# We want to allow launching from the command line, but we don't really endorse doing it manually
if __name__ == "__main__":
    start_fluxx()
