import appdaemon.plugins.hass.hassapi as hass
import datetime

class ShutdownTimer(hass.Hass):
    """
    An AppDaemon app that manages a shutdown timer for Home Assistant entities.

    The timer can be configured, started and stopped via the Lovelace UI.
    See the following example on how to integrate the timer into Home Assistant.

    Example for a bedroom sleep timer:

        ***************************************
        *  Home Assistant configuration.yaml  *
        ***************************************

        input_number:
          bedroom_timer:
          name: Timer
          initial: 30
          min: 1
          max: 240
          step: 1

        sensor:
          - platform: template
            sensors:
              bedroom_timer:
                value_template: 'off'

        script:
          start_bedroom_timer:
            sequence:
            - event: start_bedroom_timer_event
              event_data:
                state: 'activated'
          stop_bedroom_timer:
            sequence:
            - event: stop_bedroom_timer_event
              event_data:
                state: 'activated'

        **************************
        *  AppDaemon apps.yaml:  *
        **************************

        ---
        sleep_timer_bedroom:
          module: shutdown_timer
          class: ShutdownTimer
          start_event: start_bedroom_timer_event
          stop_event: stop_bedroom_timer_event
          shutdown_entities:
            - switch.bedroom_media_switch
            - light.bedroom_light
          number_entity: input_number.bedroom_timer
          sensor_entity: sensor.bedroom_timer

        *******************************
        *  Lovelace UI entities card  *
        *******************************

        entities:
          - entity: sensor.bedroom_timer
          - entity: input_number.bedroom_timer
          - entity: script.start_bedroom_timer
            icon: 'mdi:play'
            name: Start
          - entity: script.stop_bedroom_timer
            icon: 'mdi:stop'
            name: Stop
        show_header_toggle: false
        type: entities
        title: Sleep timer

    """
    def initialize(self):

        # The name of the start event that HA needs to fire to start a new timer
        self.start_event = self.args["start_event"]
        # The name of the stop event that HA needs to fire to stop a running timer
        self.stop_event = self.args["stop_event"]
        # The HA entities on which the turn_off service will be called
        self.shutdown_entities = self.args["shutdown_entity"]
        # The name of the input_number containing the shutdown time
        self.number_entity = self.args["number_entity"]
        # The name of the sensor displaying the remaining minutes until shutdown
        self.sensor_entity = self.args["sensor_entity"]

        self.check_entities(self.number_entity, self.sensor_entity)
        self.check_entities(self.shutdown_entities)

        # Register the listeners that call the start_timer and the stop timer function if
        # if the respective events are fired in Home Assistant
        self.listen_event(self.start_timer, event=self.start_event)
        self.listen_event(self.stop_timer, event=self.stop_event)
        # A handle to the currently running shutdown timer
        self.timer_handle = None
        # A handle for the scheduler updating the sensor entity with the remaining minutes of the timer
        self.update_countdown_handle = None
        # Remaining minutes of the currently running shutdown timer
        self.shutdown_counter = 0

    def start_timer(self, *args):
        """
        Function invoked by the start_timer event listener.
        Starts a new timer. Calling the function will cancel a running timer.
        :param args: The arguments the event listener passes to the start_timer callback.

        """

        # if a timer is running, cancel the timer and the update scheduler
        if self.timer_handle != None:
            self.cancel_timer(self.timer_handle)
            self.cancel_timer(self.update_countdown_handle)

        now = datetime.datetime.now()

        # try to fetch the shutdown minutes
        try:
            val = self.get_state(self.number_entity)
            shutdown_minutes = int(float(val))
        except ValueError:
            shutdown_minutes = 0
            self.error(f"Could not convert the value {val} fetched by self.get_state({self.number_entity}) to an integer.")

        if shutdown_minutes > 0:
            # set the shutdown counter of the class
            self.shutdown_counter = shutdown_minutes
            # determine the time of the entity shutdown
            shutdown_time = now + datetime.timedelta(minutes=shutdown_minutes)
            self.log(f"Shutdown of {self.shutdown_entity} at {shutdown_time}.")
            # create a new shutdown timer and initially set the sensor displaying the remaining minutes
            self.timer_handle = self.run_at(self.shutdown, shutdown_time)
            self.set_state(self.sensor_entity, state=f"{self.shutdown_counter} min")
            # create an update scheduler for the sensor displaying the remaining minutes
            self.update_countdown_handle = self.run_minutely(self.update_countdown, start=None)

    def stop_timer(self, *args):
        """
        Function invoked by the stop_timer event listener.
        Stops a running timer.

        :param args: The arguments the event listener passes to the stop_timer callback.

        """
        # if a running timer exists, cancel it and stop updating the sensor displaying the remaining minutes
        if self.timer_handle != None:
            self.cancel_timer(self.timer_handle)
            self.set_state(self.sensor_entity, state="off")
            self.cancel_timer(self.update_countdown_handle)
            self.update_countdown_handle = None
            self.timer_handle = None
            self.log(f"Shutdown timer of {self.shutdown_entity} stopped.")

    def update_countdown(self, *args):
        """
        Function invoked by the update scheduler. Decreases the shutdown counter and
        sets the value of the sensor displaying the remaining minutes

        :param args: The arguments the update scheduler passes to the update_countdown callback.

        """
        self.shutdown_counter -= 1
        if self.shutdown_counter > 0:
            self.set_state(self.sensor_entity, state=f"{self.shutdown_counter} min")
        else:
            self.set_state(self.sensor_entity, state="off")
            self.cancel_timer(self.update_countdown_handle)

    def shutdown(self, *args):
        for entity in self.shutdown_entities:

            self.log(f"Shutting down {entity}.")
            self.turn_off(entity)

    def check_entities(self, *args):
        """
        Checks if the passed entities exist in Home Assistant.
        :param args: A list of Strings containing Home Assistant entities

        """
        for entity in args:
            if not self.entity_exists(entity):
                self.error(f"Could not find the entity {entity} in HomeAssistant.")

