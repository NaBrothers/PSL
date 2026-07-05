# Spec: Web Home

## ADDED Requirements

### Requirement: Pixel Club Base Home
The system SHALL render the authenticated `/home` route as a pixel-art football club base instead of a dashboard-style menu page.

#### Scenario: Home displays a club base scene
- **GIVEN** an authenticated user opens `/home`
- **WHEN** the home page loads
- **THEN** the page displays a Phaser-rendered pixel club facility map
- **AND** the map visually includes football club facilities such as a pitch, training center, academy, scout center, commerce center, medical center, and clubhouse
- **AND** the existing global status header and bottom tab bar remain available

### Requirement: Programmatic First-Version Assets
The system SHALL generate first-version pixel map assets programmatically without requiring an external tileset.

#### Scenario: Scene initializes without external tileset files
- **WHEN** the club base scene starts
- **THEN** it creates visible grass, road, building, decoration, and player sprite textures in code
- **AND** no external Tiled JSON or tileset file is required to render the first version

### Requirement: Starting XI Agents
The system SHALL display current starting squad players as walking agents in the club base scene.

#### Scenario: Starting players appear with names
- **GIVEN** the squad endpoint returns starting cards
- **WHEN** the home scene receives squad data
- **THEN** each non-empty starting card is represented by a walking pixel agent
- **AND** each agent displays a visible player nameplate
- **AND** clicking an agent navigates to that card's detail page

### Requirement: Building Interaction Drawer
The system SHALL open a React bottom drawer when a building is selected from the Phaser scene.

#### Scenario: Building click opens details
- **WHEN** the user clicks a club facility in the scene
- **THEN** a bottom drawer opens inside the home page
- **AND** the drawer shows the building name, level, status, production/effect text, and a primary action
- **AND** activating the primary action navigates to the existing feature route for that building

### Requirement: Draggable Orthogonal Map
The system SHALL render the club base as an orthogonal pixel map with a draggable camera.

#### Scenario: User pans the map
- **WHEN** the user drags on the club base canvas
- **THEN** the camera pans across the 960x640 world
- **AND** the camera remains clamped within world bounds
- **AND** no zoom gesture is required for the first version

### Requirement: Mock Building Data
The system SHALL use client-side mock data for building level, status, and production until backend building resources exist.

#### Scenario: Building data renders without backend
- **WHEN** the home page loads
- **THEN** building levels, statuses, production text, and action labels are available from local client configuration
- **AND** no club-building backend endpoint is required
