create table IF NOT EXISTS `cards` (
  `ID` int(11) NOT NULL auto_increment,
  `Player` int(11) NOT NULL,
  `User` bigint Not Null,
  `Star` int(11) NOT NULL,
  `Style` VARCHAR(20) NOT NULL,
  `Status` smallint(6) default 0,
  `Appearance` int(11) default 0,
  `Goal` int(11) default 0,
  `Assist` int(11) default 0,
  `Tackle` int(11) default 0,
  `Save` int(11) default 0,
  `Total_Appearance` int(11) default 0,
  `Total_Goal` int(11) default 0,
  `Total_Assist` int(11) default 0,
  `Total_Tackle` int(11) default 0,
  `Total_Save` int(11) default 0,
  primary key(`id`)
) default charset = utf8;
